# API Reference

## Web Interface Endpoints

### Core Endpoints

**GET `/api/v2/quick-stats`**
- Returns system health and statistics
- Response: JSON with alerts, budget, uptime

**GET `/api/v2/budget-status`**
- Returns API budget usage
- Response: JSON with daily/hourly usage

**GET `/api/v2/feed-health`**
- Returns feed connection status
- Response: JSON with connection metrics

### Trading Endpoints

**GET `/api/v2/paper-trading`**
- Returns paper trading status
- Response: JSON with positions and P&L

**POST `/api/v2/toggle-trading`**
- Enable/disable trading
- Body: `{"enabled": true/false}`

### Data Endpoints

**GET `/api/tracked`**
- Returns tracked tokens
- Query: `?limit=200`

**GET `/api/stats`**
- Returns detailed statistics
- Response: JSON with comprehensive metrics

## Configuration API

**GET `/api/config`**
- Returns current configuration
- Response: JSON with all settings

**POST `/api/config`**
- Update configuration
- Body: JSON with new settings

## WebSocket Endpoints

**WS `/ws/alerts`**
- Real-time alert stream
- Sends new alerts as they occur

**WS `/ws/status`**
- Real-time status updates
- Sends system health updates

## Authentication

All API endpoints require authentication via:
- API key in header: `X-API-Key: your-key`
- Or session cookie for web interface

## Rate Limiting

- 100 requests per minute per IP
- 1000 requests per hour per API key
- WebSocket connections: 10 per IP

## Error Responses

```json
{
  "error": "Error message",
  "code": 400,
  "details": "Additional information"
}
```

## Examples

### Get System Status
```bash
curl -H "X-API-Key: your-key" \
     http://localhost/api/v2/quick-stats
```

### Enable Trading
```bash
curl -X POST \
     -H "Content-Type: application/json" \
     -H "X-API-Key: your-key" \
     -d '{"enabled": true}' \
     http://localhost/api/v2/toggle-trading
```

### Get Tracked Tokens
```bash
curl -H "X-API-Key: your-key" \
     "http://localhost/api/tracked?limit=50"
```
