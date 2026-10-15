"""Send the deployment script to one EC2 instance and report its outcome."""
import base64
import json
import os
from pathlib import Path
import shlex
import subprocess
import time


def aws(*args):
    result = subprocess.run(
        ["aws", "--region", "us-east-1", "--no-cli-pager", "ssm", *args],
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)


def main():
    script = Path(__file__).with_name("deploy.sh").read_bytes()
    encoded = base64.b64encode(script).decode()
    image = os.environ["IMAGE_URI"]
    version = os.environ["GITHUB_SHA"]
    instance = os.environ["EC2_INSTANCE_ID"]
    command = (
        f"printf '%s' {shlex.quote(encoded)} | base64 --decode | "
        f"bash -s -- {shlex.quote(image)} {shlex.quote(version)}"
    )
    sent = aws(
        "send-command", "--instance-ids", instance,
        "--document-name", "AWS-RunShellScript", "--timeout-seconds", "120",
        "--parameters", json.dumps({"commands": [command], "executionTimeout": ["600"]}),
        "--comment", f"DeployIQ {version}",
    )
    command_id = sent["Command"]["CommandId"]
    print(f"SSM command: {command_id}", flush=True)
    deadline = time.monotonic() + 780
    while time.monotonic() < deadline:
        try:
            invocation = aws(
                "get-command-invocation", "--command-id", command_id,
                "--instance-id", instance,
            )
        except subprocess.CalledProcessError as error:
            if "InvocationDoesNotExist" not in error.stderr:
                raise
            time.sleep(5)
            continue
        status = invocation["Status"]
        if status in {"Pending", "InProgress", "Delayed", "Cancelling"}:
            time.sleep(5)
            continue
        print(invocation.get("StandardOutputContent", ""))
        print(invocation.get("StandardErrorContent", ""))
        if status != "Success":
            raise SystemExit(f"Deployment failed: {status}")
        print(f"Deployment succeeded: {image}")
        return
    raise SystemExit("Timed out waiting for SSM. Check Run Command before retrying.")


if __name__ == "__main__":
    main()
