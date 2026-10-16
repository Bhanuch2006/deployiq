"""Add Cognito and read-only dashboard routes to the existing monitoring stack."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def add_dashboard(template):
    ref = lambda name: {"Ref": name}
    sub = lambda value: {"Fn::Sub": value}
    arn = lambda name: {"Fn::GetAtt": [name, "Arn"]}
    resources = template["Resources"]
    template["Parameters"]["DashboardOrigin"] = {"Type": "String", "Default": "http://127.0.0.1:5173", "Description": "Exact frontend browser origin. Keep the default for local development."}
    table = resources["RunsTable"]["Properties"]
    table["AttributeDefinitions"] += [{"AttributeName": "repository", "AttributeType": "S"}, {"AttributeName": "received_at", "AttributeType": "S"}]
    table["GlobalSecondaryIndexes"] = [{"IndexName": "RepositoryReceivedIndex", "KeySchema": [{"AttributeName": "repository", "KeyType": "HASH"}, {"AttributeName": "received_at", "KeyType": "RANGE"}], "Projection": {"ProjectionType": "INCLUDE", "NonKeyAttributes": ["run_id", "run_attempt", "name", "conclusion", "head_sha", "head_branch", "html_url", "created_at", "run_started_at", "updated_at", "analysis_status", "analysis_source"]}}]
    resources["DashboardUsers"] = {
        "Type": "AWS::Cognito::UserPool",
        "Properties": {
            "UserPoolName": sub("${AWS::StackName}-team"),
            "UserPoolTier": "LITE",
            "AdminCreateUserConfig": {"AllowAdminCreateUserOnly": True},
            "UsernameConfiguration": {"CaseSensitive": False},
            "Policies": {"PasswordPolicy": {"MinimumLength": 12, "RequireLowercase": True, "RequireUppercase": True, "RequireNumbers": True, "RequireSymbols": True, "TemporaryPasswordValidityDays": 7}},
            "MfaConfiguration": "OFF",
        },
    }
    resources["DashboardClient"] = {
        "Type": "AWS::Cognito::UserPoolClient",
        "Properties": {"UserPoolId": ref("DashboardUsers"), "ClientName": "deployiq-dashboard", "GenerateSecret": False, "ExplicitAuthFlows": ["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"], "PreventUserExistenceErrors": "ENABLED", "IdTokenValidity": 30, "AccessTokenValidity": 30, "TokenValidityUnits": {"IdToken": "minutes", "AccessToken": "minutes"}},
    }
    resources["DashboardAuthorizer"] = {
        "Type": "AWS::ApiGatewayV2::Authorizer",
        "Properties": {"ApiId": ref("WebhookApi"), "AuthorizerType": "JWT", "Name": "DeployIQTeam", "IdentitySource": ["$request.header.Authorization"], "JwtConfiguration": {"Audience": [ref("DashboardClient")], "Issuer": sub("https://cognito-idp.${AWS::Region}.${AWS::URLSuffix}/${DashboardUsers}")}},
    }
    resources["WebhookApi"]["Properties"]["CorsConfiguration"] = {"AllowOrigins": [ref("DashboardOrigin")], "AllowMethods": ["GET", "POST", "OPTIONS"], "AllowHeaders": ["authorization", "content-type"], "MaxAge": 300}
    resources["DashboardLogs"] = {"Type": "AWS::Logs::LogGroup", "Properties": {"LogGroupName": sub("/aws/lambda/${AWS::StackName}-dashboard"), "RetentionInDays": 7}}
    resources["DashboardRole"] = {
        "Type": "AWS::IAM::Role",
        "Properties": {
            "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]},
            "Policies": [{"PolicyName": "ReadPipelineHistory", "PolicyDocument": {"Version": "2012-10-17", "Statement": [
                {"Effect": "Allow", "Action": "dynamodb:Query", "Resource": sub("${RunsTable.Arn}/index/RepositoryReceivedIndex")},
                {"Effect": "Allow", "Action": "dynamodb:GetItem", "Resource": arn("RunsTable")},
                {"Effect": "Allow", "Action": ["logs:CreateLogStream", "logs:PutLogEvents"], "Resource": sub("arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/lambda/${AWS::StackName}-dashboard:*")},
            ]}}],
        },
    }
    resources["DashboardFunction"] = {
        "Type": "AWS::Lambda::Function", "DependsOn": "DashboardLogs",
        "Properties": {"FunctionName": sub("${AWS::StackName}-dashboard"), "Runtime": "python3.12", "Handler": "index.handler", "Role": arn("DashboardRole"), "Timeout": 10, "MemorySize": 128, "Environment": {"Variables": {"RUNS_TABLE": ref("RunsTable"), "ALLOWED_REPOSITORY": ref("AllowedRepository"), "ALLOWED_REPOSITORY_ID": ref("AllowedRepositoryId")}}, "Code": {"ZipFile": (ROOT / "backend/api/reader.py").read_text()}},
    }
    resources["DashboardIntegration"] = {"Type": "AWS::ApiGatewayV2::Integration", "Properties": {"ApiId": ref("WebhookApi"), "IntegrationType": "AWS_PROXY", "IntegrationUri": arn("DashboardFunction"), "PayloadFormatVersion": "2.0"}}
    for name, route in [("DashboardListRoute", "GET /runs"), ("DashboardDetailRoute", "GET /runs/{runId}/attempts/{attempt}")]:
        resources[name] = {"Type": "AWS::ApiGatewayV2::Route", "Properties": {"ApiId": ref("WebhookApi"), "RouteKey": route, "AuthorizationType": "JWT", "AuthorizerId": ref("DashboardAuthorizer"), "Target": {"Fn::Join": ["/", ["integrations", ref("DashboardIntegration")]]}}}
    resources["AllowDashboardInvoke"] = {"Type": "AWS::Lambda::Permission", "Properties": {"Action": "lambda:InvokeFunction", "FunctionName": ref("DashboardFunction"), "Principal": "apigateway.amazonaws.com", "SourceAccount": ref("AWS::AccountId"), "SourceArn": sub("arn:${AWS::Partition}:execute-api:${AWS::Region}:${AWS::AccountId}:${WebhookApi}/*/GET/runs*")}}
    template["Outputs"].update({
        "DashboardApiUrl": {"Value": sub("https://${WebhookApi}.execute-api.${AWS::Region}.${AWS::URLSuffix}")},
        "DashboardUserPoolId": {"Value": ref("DashboardUsers")},
        "DashboardClientId": {"Value": ref("DashboardClient")},
    })
