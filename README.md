# Weather Dashboard (AWS CDK + Lambda)

CDK v2 / TypeScript infrastructure. All application logic is in the Python 3.12 Lambda
(`lambdas/weather_dashboard.py`, UI in `lambdas/dashboard.html`) — not in the stack.

- Lambda Function URL: `GET /` dashboard, `GET /api/weather?city=&units=metric|imperial`, `GET /api/history`
- Data: Open-Meteo (no API key). Search history in DynamoDB (`weather-dashboard-history`, 30-day TTL).

```bash
npm install
npm run build && npm test
npm run diff                 # preview
npm run deploy:weather_dashboard   # outputs DashboardUrl
```
