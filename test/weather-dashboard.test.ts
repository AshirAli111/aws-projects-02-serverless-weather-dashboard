import * as cdk from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import { WeatherDashboardStack } from '../lib/weather-dashboard-stack';

describe('WeatherDashboardStack', () => {
  const app = new cdk.App();
  const stack = new WeatherDashboardStack(app, 'TestStack');
  const template = Template.fromStack(stack);

  test('creates Python 3.12 Lambda with the handler module', () => {
    template.hasResourceProperties('AWS::Lambda::Function', {
      FunctionName: 'weather-dashboard-lambda',
      Runtime: 'python3.12',
      Handler: 'weather_dashboard.lambda_handler',
    });
  });

  test('creates a retained DynamoDB history table with TTL', () => {
    template.hasResource('AWS::DynamoDB::Table', {
      DeletionPolicy: 'Retain',
      Properties: {
        TableName: 'weather-dashboard-history',
        TimeToLiveSpecification: { AttributeName: 'expiresAt', Enabled: true },
      },
    });
  });

  test('exposes a public function URL', () => {
    template.hasResourceProperties('AWS::Lambda::Url', { AuthType: 'NONE' });
  });
});
