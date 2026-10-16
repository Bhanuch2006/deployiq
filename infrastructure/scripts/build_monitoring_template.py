"""Build a single uploadable CloudFormation template from the webhook source."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def ref(name):
    return {"Ref": name}


def sub(value):
    return {"Fn::Sub": value}


def arn(name):
    return {"Fn::GetAtt": [name, "Arn"]}


def build():
    template = {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "DeployIQ signed GitHub webhook ingestion: HTTP API, Lambda, DynamoDB",
        "Parameters": {
            "WebhookSecret": {"Type": "String", "NoEcho": True, "MinLength": 32, "MaxLength": 128, "Description": "Generate a random secret and enter the same value in GitHub's webhook settings. Do not commit it."},
            "AllowedRepository": {"Type": "String", "Default": "Bhanuch2006/deployiq"},
            "AllowedRepositoryId": {"Type": "String", "Default": "1421278672", "AllowedPattern": "[0-9]+"},
        },
        "Resources": {
            "RunsTable": {
                "Type": "AWS::DynamoDB::Table",
                "Properties": {
                    "TableName": sub("${AWS::StackName}-runs"), "BillingMode": "PAY_PER_REQUEST",
                    "AttributeDefinitions": [{"AttributeName": "run_key", "AttributeType": "S"}],
                    "KeySchema": [{"AttributeName": "run_key", "KeyType": "HASH"}],
                    "SSESpecification": {"SSEEnabled": True},
                },
            },
            "WebhookLogs": {
                "Type": "AWS::Logs::LogGroup",
                "Properties": {"LogGroupName": sub("/aws/lambda/${AWS::StackName}-webhook"), "RetentionInDays": 7},
            },
            "WebhookRole": {
                "Type": "AWS::IAM::Role",
                "Properties": {
                    "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]},
                    "Policies": [{"PolicyName": "StoreRunsAndWriteLogs", "PolicyDocument": {
                        "Version": "2012-10-17", "Statement": [
                            {"Effect": "Allow", "Action": "dynamodb:PutItem", "Resource": arn("RunsTable")},
                            {"Effect": "Allow", "Action": ["logs:CreateLogStream", "logs:PutLogEvents"], "Resource": sub("arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/lambda/${AWS::StackName}-webhook:*")},
                        ],
                    }}],
                },
            },
            "WebhookFunction": {
                "Type": "AWS::Lambda::Function", "DependsOn": "WebhookLogs",
                "Properties": {
                    "FunctionName": sub("${AWS::StackName}-webhook"), "Runtime": "python3.12", "Handler": "index.handler",
                    "Role": arn("WebhookRole"), "Timeout": 8, "MemorySize": 128,
                    "Environment": {"Variables": {"RUNS_TABLE": ref("RunsTable"), "WEBHOOK_SECRET": ref("WebhookSecret"), "ALLOWED_REPOSITORY": ref("AllowedRepository"), "ALLOWED_REPOSITORY_ID": ref("AllowedRepositoryId")}},
                    "Code": {"ZipFile": (ROOT / "backend/webhooks/handler.py").read_text()},
                },
            },
            "WebhookApi": {"Type": "AWS::ApiGatewayV2::Api", "Properties": {"Name": sub("${AWS::StackName}-api"), "ProtocolType": "HTTP"}},
            "WebhookIntegration": {
                "Type": "AWS::ApiGatewayV2::Integration",
                "Properties": {"ApiId": ref("WebhookApi"), "IntegrationType": "AWS_PROXY", "IntegrationUri": arn("WebhookFunction"), "PayloadFormatVersion": "2.0", "TimeoutInMillis": 10000},
            },
            "WebhookRoute": {
                "Type": "AWS::ApiGatewayV2::Route",
                "Properties": {"ApiId": ref("WebhookApi"), "RouteKey": "POST /webhooks/github", "AuthorizationType": "NONE", "Target": {"Fn::Join": ["/", ["integrations", ref("WebhookIntegration")]]}},
            },
            "WebhookStage": {
                "Type": "AWS::ApiGatewayV2::Stage",
                "Properties": {"ApiId": ref("WebhookApi"), "StageName": "$default", "AutoDeploy": True, "DefaultRouteSettings": {"ThrottlingBurstLimit": 10, "ThrottlingRateLimit": 5}},
            },
            "AllowApiInvoke": {
                "Type": "AWS::Lambda::Permission",
                "Properties": {"Action": "lambda:InvokeFunction", "FunctionName": ref("WebhookFunction"), "Principal": "apigateway.amazonaws.com", "SourceAccount": ref("AWS::AccountId"), "SourceArn": sub("arn:${AWS::Partition}:execute-api:${AWS::Region}:${AWS::AccountId}:${WebhookApi}/*/POST/webhooks/github")},
            },
        },
        "Outputs": {
            "WebhookUrl": {"Value": sub("https://${WebhookApi}.execute-api.${AWS::Region}.${AWS::URLSuffix}/webhooks/github")},
            "RunsTableName": {"Value": ref("RunsTable")},
            "WebhookFunctionName": {"Value": ref("WebhookFunction")},
        },
    }


    template["Parameters"]["GitHubTokenSecretArn"] = {
        "Type": "String",
        "Description": "ARN of an existing Secrets Manager secret whose plaintext is a fine-grained GitHub token with Actions read access to this repository.",
        "AllowedPattern": "arn:aws:secretsmanager:us-east-1:[0-9]{12}:secret:.+",
    }
    resources = template["Resources"]
    resources["RunsTable"]["Properties"]["StreamSpecification"] = {"StreamViewType": "NEW_IMAGE"}
    resources["AnalysisDeadLetterQueue"] = {
        "Type": "AWS::SQS::Queue",
        "Properties": {"MessageRetentionPeriod": 1209600, "SqsManagedSseEnabled": True},
    }
    resources["AnalysisLogs"] = {
        "Type": "AWS::Logs::LogGroup",
        "Properties": {"LogGroupName": sub("/aws/lambda/${AWS::StackName}-analyzer"), "RetentionInDays": 7},
    }
    resources["AnalysisRole"] = {
        "Type": "AWS::IAM::Role",
        "Properties": {
            "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]},
            "Policies": [{"PolicyName": "AnalyzeFailedRuns", "PolicyDocument": {"Version": "2012-10-17", "Statement": [
                {"Effect": "Allow", "Action": ["dynamodb:GetItem", "dynamodb:UpdateItem"], "Resource": arn("RunsTable")},
                {"Effect": "Allow", "Action": ["dynamodb:DescribeStream", "dynamodb:GetRecords", "dynamodb:GetShardIterator"], "Resource": {"Fn::GetAtt": ["RunsTable", "StreamArn"]}},
                {"Effect": "Allow", "Action": "dynamodb:ListStreams", "Resource": "*"},
                {"Effect": "Allow", "Action": "secretsmanager:GetSecretValue", "Resource": ref("GitHubTokenSecretArn")},
                {"Effect": "Allow", "Action": "bedrock:InvokeModel", "Resource": sub("arn:${AWS::Partition}:bedrock:${AWS::Region}::foundation-model/amazon.nova-micro-v1:0")},
                {"Effect": "Allow", "Action": "sqs:SendMessage", "Resource": arn("AnalysisDeadLetterQueue")},
                {"Effect": "Allow", "Action": ["logs:CreateLogStream", "logs:PutLogEvents"], "Resource": sub("arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/lambda/${AWS::StackName}-analyzer:*")},
            ]}}],
        },
    }
    resources["AnalysisFunction"] = {
        "Type": "AWS::Lambda::Function", "DependsOn": "AnalysisLogs",
        "Properties": {
            "FunctionName": sub("${AWS::StackName}-analyzer"), "Runtime": "python3.12", "Handler": "index.handler",
            "Role": arn("AnalysisRole"), "Timeout": 180, "MemorySize": 256,
            "Environment": {"Variables": {"RUNS_TABLE": ref("RunsTable"), "ALLOWED_REPOSITORY": ref("AllowedRepository"), "ALLOWED_REPOSITORY_ID": ref("AllowedRepositoryId"), "GITHUB_TOKEN_SECRET_ARN": ref("GitHubTokenSecretArn"), "BEDROCK_MODEL_ID": "amazon.nova-micro-v1:0"}},
            "Code": {"ZipFile": (ROOT / "backend/analysis/worker.py").read_text()},
        },
    }
    resources["AnalysisStreamMapping"] = {
        "Type": "AWS::Lambda::EventSourceMapping",
        "Properties": {
            "FunctionName": ref("AnalysisFunction"), "EventSourceArn": {"Fn::GetAtt": ["RunsTable", "StreamArn"]},
            "StartingPosition": "LATEST", "BatchSize": 1, "MaximumRetryAttempts": 2,
            "MaximumRecordAgeInSeconds": 3600,
            "DestinationConfig": {"OnFailure": {"Destination": arn("AnalysisDeadLetterQueue")}},
            "FilterCriteria": {"Filters": [{"Pattern": json.dumps({"eventName": ["INSERT"], "dynamodb": {"NewImage": {"conclusion": {"S": ["failure", "timed_out"]}}}})}]},
        },
    }
    template["Outputs"]["AnalysisFunctionName"] = {"Value": ref("AnalysisFunction")}
    template["Outputs"]["AnalysisDeadLetterQueueUrl"] = {"Value": ref("AnalysisDeadLetterQueue")}
    return template


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    destination = ROOT / "infrastructure/monitoring-stack.json"
    content = json.dumps(build(), indent=2) + "\n"
    if args.check:
        if not destination.exists() or destination.read_text() != content:
            raise SystemExit("Monitoring template is stale; run python infrastructure/scripts/build_monitoring_template.py")
        print("Monitoring template matches webhook source")
    else:
        destination.write_text(content)
        print(destination)
