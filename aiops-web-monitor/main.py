"""FastAPI backend for AIOps Monitor."""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import httpx
import os
import json

app = FastAPI(title="AIOps Monitor")

# 配置文件路径
CONFIG_FILE = "config.json"

# 默认配置
DEFAULT_CONFIG = {
    "aiops_api": "",
    "agent_runtime_arn": ""
}

def load_config():
    """加载配置"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(config):
    """保存配置"""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

async def call_aiops_api(action: str, **kwargs):
    config = load_config()
    aiops_api = config.get('aiops_api', '')
    if not aiops_api:
        return None
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.post(aiops_api, json={"action": action, **kwargs})
            return resp.json() if resp.status_code == 200 else None
        except Exception as e:
            print(f"API call error: {e}")
            return None

@app.get("/api/config")
async def get_config():
    """获取当前配置"""
    config = load_config()
    return {
        "aiops_api": config.get('aiops_api', '').strip(),
        "agent_runtime_arn": config.get('agent_runtime_arn', '').strip(),
        "configured": bool(config.get('aiops_api', '').strip() and config.get('agent_runtime_arn', '').strip())
    }

@app.get("/api/health")
async def check_health():
    """检查 API 连接状态"""
    config = load_config()
    aiops_api = config.get('aiops_api', '').strip()
    
    if not aiops_api:
        return {"connected": False, "error": "API URL not configured"}
    
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            # 尝试调用 list_alarms 来验证连接
            resp = await client.post(aiops_api, json={"action": "list_alarms"})
            if resp.status_code == 200:
                return {"connected": True}
            else:
                return {"connected": False, "error": f"API returned status {resp.status_code}"}
        except httpx.TimeoutException:
            return {"connected": False, "error": "Connection timeout"}
        except httpx.ConnectError as e:
            return {"connected": False, "error": f"Connection failed: {str(e)}"}
        except Exception as e:
            return {"connected": False, "error": str(e)}

@app.post("/api/config")
async def update_config(data: dict):
    """更新配置"""
    config = load_config()
    if 'aiops_api' in data:
        config['aiops_api'] = data['aiops_api']
    if 'agent_runtime_arn' in data:
        config['agent_runtime_arn'] = data['agent_runtime_arn']
    save_config(config)
    return {"success": True, "config": config}

@app.get("/api/alarms")
async def get_alarms():
    data = await call_aiops_api("list_alarms")
    return data.get("alarms", []) if data else []

@app.get("/api/investigations")
async def get_investigations():
    data = await call_aiops_api("get_investigations")
    return data.get("investigations", []) if data else []

@app.get("/api/investigation/{inv_id}")
async def get_investigation(inv_id: str):
    data = await call_aiops_api("get_investigation", investigation_id=inv_id)
    if not data:
        return {"error": "Investigation not found"}
    
    ctx = data.get('context', {})
    findings = ctx.get('findings', {})
    tasks = data.get('tasks', [])
    
    for task in tasks:
        task_id = task.get('task_id', '')
        agent_type = task.get('agent_type', '')
        finding_key = f"{task_id}_{agent_type}"
        task['finding'] = findings.get(finding_key) or findings.get(task_id) or findings.get(agent_type)
    
    data['tasks'] = tasks
    return data

@app.get("/api/investigated-alarms")
async def get_investigated_alarms():
    """获取已调查的告警名称列表"""
    data = await call_aiops_api("get_investigations")
    if not data:
        return []
    alarm_names = []
    for inv in data.get("investigations", []):
        alarm_name = inv.get("alarm_summary", {}).get("resource_name")
        if alarm_name:
            alarm_names.append(alarm_name)
    return alarm_names

@app.post("/api/clear")
async def clear_data():
    """清空所有调查数据"""
    result = await call_aiops_api("clear_investigations")
    return {"success": True, "message": "Clear request sent"}

@app.post("/api/investigate")
async def start_investigation(alarm: dict):
    config = load_config()
    agent_runtime_arn = config.get('agent_runtime_arn', '')
    
    if not agent_runtime_arn:
        return {"success": False, "error": "Agent Runtime ARN not configured"}
    
    prompt = f"""CloudWatch Alarm: {alarm.get('name')}
Namespace: {alarm.get('namespace')}
Metric: {alarm.get('metric_name')}
Dimensions: {alarm.get('dimensions_str', '')}
Threshold: {alarm.get('comparison_operator', '')} {alarm.get('threshold', '')}
State Reason: {alarm.get('state_reason', '')}
Time: {alarm.get('state_updated', '')}"""
    
    result = await call_aiops_api("invoke_agent", prompt=prompt, agent_runtime_arn=agent_runtime_arn)
    return {"success": bool(result)}

@app.get("/", response_class=HTMLResponse)
async def index():
    return open("static/index.html").read()

app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
