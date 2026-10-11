import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as path from 'path';

export class WeatherDashboardStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Search history: one row per lookup, expires automatically via TTL.
    const historyTable = new dynamodb.Table(this, 'WeatherHistoryTable', {
      tableName: 'weather-dashboard-history',
      partitionKey: { name: 'pk', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'ts', type: dynamodb.AttributeType.NUMBER },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      timeToLiveAttribute: 'expiresAt',
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    // All logic lives in lambdas/weather_dashboard.py (and dashboard.html).
    const weatherLambda = new lambda.Function(this, 'WeatherDashboardLambda', {
      functionName: 'weather-dashboard-lambda',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'weather_dashboard.lambda_handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '..', 'lambdas')),
      timeout: cdk.Duration.seconds(15),
      memorySize: 256,
      logGroup: new logs.LogGroup(this, 'WeatherDashboardLogGroup', {
        retention: logs.RetentionDays.ONE_MONTH,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }),
      environment: {
        HISTORY_TABLE_NAME: historyTable.tableName,
      },
    });

    historyTable.grantReadWriteData(weatherLambda);

    // Public HTTPS endpoint: GET / (dashboard), GET /api/weather, GET /api/history
    const fnUrl = weatherLambda.addFunctionUrl({
      authType: lambda.FunctionUrlAuthType.NONE,
    });

    new cdk.CfnOutput(this, 'DashboardUrl', {
      value: fnUrl.url,
      description: 'Open this URL in a browser to use the Weather Dashboard',
    });
  }
}
