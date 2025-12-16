#!/usr/bin/env python3
from flask import Flask, render_template, jsonify, request
import requests
import threading
import time
import json
import os

app = Flask(__name__)

CONFIG_FILE = "config.json"

# Scenario definitions
SCENARIOS = {
    's3_access': {
        'name': '场景1: S3访问拒绝',
        'description': '通过Bucket Policy阻止S3写入，模拟权限配置错误',
        'alarm': 'PostItems-5XX',
        'request_type': 'post_items'
    },
    'latency': {
        'name': '场景2: API延迟',
        'description': '注入3000ms延迟到GET /items接口，模拟网络或后端响应慢',
        'alarm': 'GetAllItems-Latency',
        'request_type': 'get_items'
    },
    'wrong_ids': {
        'name': '场景3: 资源不存在(404)',
        'description': '返回404错误，模拟请求不存在的资源ID',
        'alarm': 'GetItemById-4XX',
        'request_type': 'get_by_id'
    },
    'lambda_throttle': {
        'name': '场景4: Lambda限流',
        'description': '限制Lambda并发为1，模拟高并发下的429限流错误',
        'alarm': 'PostItems-4XX',
        'request_type': 'post_items'
    },
    'dynamodb_throttle': {
        'name': '场景5: DynamoDB限流',
        'description': '模拟DynamoDB吞吐量超限，返回500错误',
        'alarm': 'PostItems-5XX',
        'request_type': 'post_items'
    }
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {
        "error_injection_api": "",
        "sample_api": ""
    }

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

# Global state for request threads
request_threads = {}
stop_events = {}
recovery_mode = {}  # Track if scenario is in recovery mode (sending normal requests)

def send_single_request(config, request_type):
    """Send a single request based on request type"""
    try:
        if request_type == 'get_items':
            requests.get(f"{config['sample_api']}/items", timeout=5)
        elif request_type == 'get_by_id':
            requests.get(f"{config['sample_api']}/items/test-id-1", timeout=5)
        else:  # post_items
            test_data = {"name": "Error Trigger", "content": f"Request at {time.time()}"}
            requests.post(f"{config['sample_api']}/items", json=test_data, timeout=5)
    except Exception as e:
        print(f"Request failed: {e}")

def send_continuous_requests(scenario_type, max_requests=None):
    """Send continuous requests based on scenario type
    
    Args:
        scenario_type: Type of scenario to send requests for
        max_requests: If set, stop after this many requests (used for recovery)
    """
    stop_event = stop_events.get(scenario_type)
    if not stop_event:
        return
    
    request_count = 0
    while not stop_event.is_set():
        # Check if we've reached max requests limit
        if max_requests and request_count >= max_requests:
            print(f"Recovery requests completed ({request_count}/{max_requests}) for {scenario_type}")
            break
            
        try:
            config = load_config()
            scenario = SCENARIOS.get(scenario_type, {})
            request_type = scenario.get('request_type', 'post_items')
            
            # For lambda_throttle, send concurrent requests to trigger 429
            if scenario_type == 'lambda_throttle':
                # Send 5 concurrent requests to trigger throttling
                threads = []
                for _ in range(5):
                    t = threading.Thread(target=send_single_request, args=(config, request_type))
                    t.start()
                    threads.append(t)
                for t in threads:
                    t.join(timeout=10)
                request_count += 5
            else:
                send_single_request(config, request_type)
                request_count += 1
        except Exception as e:
            print(f"Request failed ({scenario_type}): {e}")
        time.sleep(2)

def start_requests(scenario_type, max_requests=None, is_recovery=False):
    """Start continuous requests for a scenario
    
    Args:
        scenario_type: Type of scenario
        max_requests: If set, stop after this many requests
        is_recovery: If True, this is recovery mode (sending normal requests after fix)
    """
    global request_threads, stop_events, recovery_mode
    
    # Stop any existing thread for this scenario
    if scenario_type in stop_events:
        stop_events[scenario_type].set()
        if scenario_type in request_threads and request_threads[scenario_type].is_alive():
            request_threads[scenario_type].join(timeout=3)
    
    # Set recovery mode flag
    recovery_mode[scenario_type] = is_recovery
    
    # Create new stop event and thread
    stop_events[scenario_type] = threading.Event()
    request_threads[scenario_type] = threading.Thread(
        target=send_continuous_requests, 
        args=(scenario_type, max_requests),
        daemon=True
    )
    request_threads[scenario_type].start()

def stop_requests(scenario_type):
    """Stop continuous requests for a scenario"""
    if scenario_type in stop_events:
        stop_events[scenario_type].set()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/config', methods=['GET'])
def get_config():
    config = load_config()
    return jsonify({
        "error_injection_api": config.get('error_injection_api', ''),
        "sample_api": config.get('sample_api', ''),
        "configured": bool(config.get('error_injection_api') and config.get('sample_api'))
    })

@app.route('/api/config', methods=['POST'])
def update_config():
    data = request.json
    config = load_config()
    if 'error_injection_api' in data:
        config['error_injection_api'] = data['error_injection_api']
    if 'sample_api' in data:
        config['sample_api'] = data['sample_api']
    save_config(config)
    return jsonify({"success": True, "config": config})

@app.route('/api/scenarios')
def get_scenarios():
    return jsonify(SCENARIOS)

@app.route('/api/check-connection', methods=['POST'])
def check_connection():
    """Check if the configured APIs are reachable"""
    data = request.json
    error_api = data.get('error_injection_api', '')
    sample_api = data.get('sample_api', '')
    
    if not error_api or not sample_api:
        return jsonify({"connected": False, "error": "API 地址未配置"})
    
    errors = []
    
    # Check Error Injection API
    try:
        response = requests.post(error_api, json={"action": "status"}, timeout=5)
        if response.status_code != 200:
            errors.append(f"Error Injection API 返回 {response.status_code}")
    except requests.exceptions.Timeout:
        errors.append("Error Injection API 连接超时")
    except requests.exceptions.ConnectionError:
        errors.append("Error Injection API 无法连接")
    except Exception as e:
        errors.append(f"Error Injection API: {str(e)}")
    
    # Check Sample API
    try:
        response = requests.get(f"{sample_api}/items", timeout=5)
        # Accept any response (even 4xx/5xx) as long as we can connect
        if response.status_code >= 500:
            # Only fail on server errors, 4xx might be expected
            pass
    except requests.exceptions.Timeout:
        errors.append("Sample API 连接超时")
    except requests.exceptions.ConnectionError:
        errors.append("Sample API 无法连接")
    except Exception as e:
        errors.append(f"Sample API: {str(e)}")
    
    if errors:
        return jsonify({"connected": False, "error": "; ".join(errors)})
    
    return jsonify({"connected": True})

@app.route('/api/status')
def get_status():
    try:
        config = load_config()
        response = requests.post(config['error_injection_api'], json={"action": "status"}, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # Add request thread status with recovery mode info
            data['active_requests'] = {
                k: v.is_alive() if v else False 
                for k, v in request_threads.items()
            }
            data['recovery_requests'] = {
                k: (v.is_alive() if v else False) and recovery_mode.get(k, False)
                for k, v in request_threads.items()
            }
            return jsonify(data)
        else:
            return jsonify({"error": "Failed to get status"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/inject/<scenario_type>', methods=['POST'])
def inject_error(scenario_type):
    if scenario_type not in SCENARIOS:
        return jsonify({"error": f"Unknown scenario: {scenario_type}"}), 400
    
    try:
        config = load_config()
        response = requests.post(
            config['error_injection_api'], 
            json={"action": "inject", "error_type": scenario_type}, 
            timeout=15
        )
        if response.status_code == 200:
            # Start continuous requests for this scenario (not recovery mode)
            start_requests(scenario_type, is_recovery=False)
            result = response.json()
            result['message'] = f"{SCENARIOS[scenario_type]['name']} injected, continuous requests started"
            return jsonify(result)
        else:
            return jsonify({"error": "Failed to inject error", "details": response.text}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/recover/<scenario_type>', methods=['POST'])
def recover_error(scenario_type):
    if scenario_type not in SCENARIOS:
        return jsonify({"error": f"Unknown scenario: {scenario_type}"}), 400
    
    try:
        # Stop error injection requests first
        stop_requests(scenario_type)
        
        config = load_config()
        response = requests.post(
            config['error_injection_api'], 
            json={"action": "recover", "error_type": scenario_type}, 
            timeout=15
        )
        if response.status_code == 200:
            # After recovery, send 30 normal requests to help alarm recover
            # This simulates real-world scenario where customer requests continue after fix
            start_requests(scenario_type, max_requests=30, is_recovery=True)
            
            result = response.json()
            result['message'] = f"{SCENARIOS[scenario_type]['name']} recovered, sending 30 normal requests to restore alarm"
            return jsonify(result)
        else:
            return jsonify({"error": "Failed to recover error", "details": response.text}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/recover-all', methods=['POST'])
def recover_all():
    """Recover all scenarios"""
    results = {}
    config = load_config()
    
    for scenario_type in SCENARIOS.keys():
        try:
            stop_requests(scenario_type)
            response = requests.post(
                config['error_injection_api'], 
                json={"action": "recover", "error_type": scenario_type}, 
                timeout=10
            )
            results[scenario_type] = 'recovered' if response.status_code == 200 else 'failed'
        except Exception as e:
            results[scenario_type] = f'error: {str(e)}'
    
    return jsonify({"message": "All scenarios recovered", "results": results})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8082)
