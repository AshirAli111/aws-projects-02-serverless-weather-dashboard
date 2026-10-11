#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { WeatherDashboardStack } from '../lib/weather-dashboard-stack';

const app = new cdk.App();

new WeatherDashboardStack(app, 'weather-dashboard-stack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION ?? 'us-east-1',
  },
});
