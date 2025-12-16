# AIOps Web Demo - Error Injection & Alarm Monitor

A web-based interface for demonstrating AWS CloudWatch alarm behavior through S3 error injection.

## Features

- 🎛️ **One-click Error Injection**: Inject and recover from S3 access errors
- 📊 **Real-time Alarm Details**: View CloudWatch alarm details in email format
- 🧪 **API Testing**: Test the sample API to verify error behavior
- 🔄 **Auto-refresh**: Automatically updates status every 30 seconds

## Quick Start

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the web application**:
   ```bash
   python app.py
   ```

3. **Open in browser**:
   ```
   http://localhost:5000
   ```

## Usage

### Error Injection Workflow

1. **Check Status**: View current error injection status
2. **Inject Error**: Click "Inject S3 Error" to simulate S3 access failures
3. **Monitor Alarms**: Watch the alarm details update to show ALARM state
4. **Test API**: Use "Test API" to verify the API returns 502 errors
5. **Recover**: Click "Recover from Error" to restore normal operation

### Alarm Details

The web interface displays CloudWatch alarm details in the same format as SNS email notifications, including:

- **Alarm Information**: Name, description, state, and timestamps
- **Threshold Configuration**: Metric details and evaluation criteria
- **Monitored Resource**: API Gateway endpoint information
- **State Change Actions**: SNS topic and notification settings
- **Error Injection Status**: Current S3 bucket policy status

## Architecture

```
Web Browser → Flask App → Error Injection API → AWS Resources
     ↓              ↓              ↓              ↓
  User Interface   Backend      Lambda Function   S3/CloudWatch
```

## Resource Information

The alarm details are dynamically populated with your actual AWS resources (configured via CloudFormation Outputs):

- **API Name**: `{stack-name}-sample-api`
- **Alarm**: `{stack-name}-PostItems-5XX`
- **S3 Bucket**: `{stack-name}-content-{account-id}`

## Development

- **Backend**: Python Flask
- **Frontend**: HTML5 + CSS3 + Vanilla JavaScript
- **API Integration**: RESTful endpoints for error injection
- **Real-time Updates**: Auto-refresh and manual refresh options

## Troubleshooting

- **Connection Error**: Ensure the error injection API is accessible
- **Alarm Not Updating**: Wait 1-2 minutes for CloudWatch metrics to propagate
- **Port Conflict**: Change the port in `app.py` if 5000 is in use
