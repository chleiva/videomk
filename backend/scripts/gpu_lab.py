#!/usr/bin/env python3
"""GPU lab: ONE short-lived GPU instance for model experiments (avatars / lip sync), with hard cost guardrails. docs/AVATARS.md.

Every guardrail is independent of the others, so one failing does not leave a machine running:
  1. Account quota: 8 G-family vCPUs on QA in us-east-1 = at most one single-GPU instance can exist.
  2. This script refuses to start a second lab instance, refuses any type not in ALLOWED, and refuses a lifetime above MAX_MINUTES_CAP.
  3. Inside the instance, the FIRST line of user data schedules `shutdown` at the deadline; shutdown behaviour is TERMINATE (not stop), so nothing keeps billing.
  4. Inside the instance, an idle watchdog shuts down when the GPU has been idle for IDLE_MINUTES.
  5. Outside the instance, a one-time EventBridge Scheduler rule terminates it shortly after the deadline even if the instance's own timers never ran.
  6. `sweep` terminates any lab instance older than its deadline tag (run it any time; `up` runs it first).
  7. The disk is deleted on termination; there is no public port (access is SSM only), no Elastic IP, no spot, no auto scaling, no restart.
Only on-demand, only the QA account, only us-east-1.

  gpu_lab.py up [--type g6.xlarge] [--minutes 120]     start (prints the worst-case cost first)
  gpu_lab.py status                                      what is running, age, time left, cost so far
  gpu_lab.py run 'shell command' [--timeout 3600]        run on the instance through SSM and print the output
  gpu_lab.py down                                        terminate now and remove the backstop
  gpu_lab.py sweep                                       terminate anything past its deadline
"""
import argparse
import base64
import datetime as dt
import json
import sys
import time

import boto3

# Region: us-east-1 (owner decision 2026-11-26, after AWS closed the Stockholm quota request). It has every current GPU family and the lowest prices of all
# (about 6% under Stockholm). The lab only exchanges small files with the QA bucket in eu-west-1, so the distance does not matter.
PROFILE, REGION, ACCOUNT = "qa", "us-east-1", "552357225438"
TAG = {"Key": "project", "Value": "videomk-gpu-lab"}
# On-demand USD per hour in us-east-1, read from the AWS price list on 2026-11-26 (the bill is the truth). All are single-GPU and at most 8 vCPUs, so the quota
# (8 vCPUs) allows exactly one. Which is cheapest PER PRESENTER MINUTE depends on measured speed: the prototype measures it, docs/AVATARS.md records it.
ALLOWED = {
    "g4dn.xlarge": 0.526,    # T4 16 GB (2019): cheapest hour, slowest
    "g6.xlarge": 0.8048,     # L4 24 GB (2024): the efficient default for a light model such as MuseTalk
    "g6.2xlarge": 0.9776,    # L4 24 GB, more CPU and memory for video encode/decode
    "g5.xlarge": 1.006,      # A10G 24 GB (2022): faster than L4, older
    "g6e.xlarge": 1.861,     # L40S 48 GB (2024): for heavy models (InfiniteTalk) that need the memory
    "g6e.2xlarge": 2.242,
    "g7.2xlarge": 2.52,    # RTX PRO 4500 Blackwell 32 GB (newest generation)
}
MAX_MINUTES_CAP = 240           # no session may be longer than 4 hours
DEFAULT_MINUTES = 120
IDLE_MINUTES = 25               # GPU below 5% for this long: shut down
BACKSTOP_GRACE_MIN = 10         # the outside terminate fires this long after the deadline
DISK_GB = 150
DISK_USD_PER_GB_MONTH = 0.088
BUCKET = f"videomk-qa-{ACCOUNT}"
LAB_PREFIX = "lab/avatars/"     # the only S3 prefix the instance may read or write
ROLE, PROFILE_NAME, SCHED_ROLE, SG_NAME = "videomk-gpu-lab-instance", "videomk-gpu-lab-instance", "videomk-gpu-lab-backstop", "videomk-gpu-lab-no-inbound"
AMI_PARAM = "/aws/service/deeplearning/ami/x86_64/oss-nvidia-driver-gpu-pytorch-2.6-ubuntu-22.04/latest/ami-id"


def session():
    s = boto3.Session(profile_name=PROFILE, region_name=REGION)
    if s.client("sts").get_caller_identity()["Account"] != ACCOUNT:
        sys.exit("refusing: not the QA account")
    return s


def worst_case_usd(itype: str, minutes: int) -> float:
    hours = (minutes + BACKSTOP_GRACE_MIN) / 60
    return round(ALLOWED[itype] * hours + DISK_GB * DISK_USD_PER_GB_MONTH / 730 * hours, 2)


def user_data(minutes: int) -> str:
    # Line 2 is the deadline: it is scheduled before anything else can fail.
    return f"""#!/bin/bash
shutdown -h +{minutes} "gpu lab deadline"
cat > /usr/local/bin/idle-watchdog.sh <<'EOF'
#!/bin/bash
# shut down when the GPU has been idle for {IDLE_MINUTES} minutes (checked once a minute; the first 15 minutes are setup time and never count)
idle=0
sleep 900
while true; do
  u=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null | head -1)
  if [ -z "$u" ] || [ "$u" -lt 5 ]; then idle=$((idle+1)); else idle=0; fi
  if [ "$idle" -ge {IDLE_MINUTES} ]; then shutdown -h now "gpu lab idle"; fi
  sleep 60
done
EOF
chmod +x /usr/local/bin/idle-watchdog.sh
nohup /usr/local/bin/idle-watchdog.sh >/var/log/idle-watchdog.log 2>&1 &
mkdir -p /lab && chown ubuntu:ubuntu /lab
"""


def lab_instances(ec2, states=("pending", "running", "stopping", "stopped")):
    r = ec2.describe_instances(Filters=[{"Name": f"tag:{TAG['Key']}", "Values": [TAG["Value"]]}, {"Name": "instance-state-name", "Values": list(states)}])
    return [i for res in r["Reservations"] for i in res["Instances"]]


def tag(inst, key):
    return next((t["Value"] for t in inst.get("Tags", []) if t["Key"] == key), "")


def ensure_roles(s):
    iam = s.client("iam")
    def role(name, service, policy):
        try:
            iam.get_role(RoleName=name)
        except iam.exceptions.NoSuchEntityException:
            iam.create_role(RoleName=name, Tags=[TAG], AssumeRolePolicyDocument=json.dumps({"Version": "2012-10-17", "Statement": [
                {"Effect": "Allow", "Principal": {"Service": service}, "Action": "sts:AssumeRole"}]}))
        iam.put_role_policy(RoleName=name, PolicyName="lab", PolicyDocument=json.dumps({"Version": "2012-10-17", "Statement": policy}))
    role(ROLE, "ec2.amazonaws.com", [
        {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject"], "Resource": f"arn:aws:s3:::{BUCKET}/{LAB_PREFIX}*"},
        {"Effect": "Allow", "Action": "s3:ListBucket", "Resource": f"arn:aws:s3:::{BUCKET}", "Condition": {"StringLike": {"s3:prefix": f"{LAB_PREFIX}*"}}}])
    iam.attach_role_policy(RoleName=ROLE, PolicyArn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore")
    try:
        iam.get_instance_profile(InstanceProfileName=PROFILE_NAME)
    except iam.exceptions.NoSuchEntityException:
        iam.create_instance_profile(InstanceProfileName=PROFILE_NAME)
        iam.add_role_to_instance_profile(InstanceProfileName=PROFILE_NAME, RoleName=ROLE)
        time.sleep(12)   # IAM is eventually consistent
    # the backstop may terminate ONLY instances carrying the lab tag
    role(SCHED_ROLE, "scheduler.amazonaws.com", [
        {"Effect": "Allow", "Action": "ec2:TerminateInstances", "Resource": f"arn:aws:ec2:{REGION}:{ACCOUNT}:instance/*",
         "Condition": {"StringEquals": {f"aws:ResourceTag/{TAG['Key']}": TAG["Value"]}}}])


def ensure_sg(ec2) -> str:
    vpc = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])["Vpcs"][0]["VpcId"]
    g = ec2.describe_security_groups(Filters=[{"Name": "group-name", "Values": [SG_NAME]}, {"Name": "vpc-id", "Values": [vpc]}])["SecurityGroups"]
    if g:
        return g[0]["GroupId"]
    return ec2.create_security_group(GroupName=SG_NAME, Description="GPU lab: no inbound at all (SSM only)", VpcId=vpc,
                                     TagSpecifications=[{"ResourceType": "security-group", "Tags": [TAG]}])["GroupId"]   # a new group has no inbound rules


def backstop_name(iid: str) -> str:
    return f"gpu-lab-terminate-{iid}"


def cmd_sweep(s, quiet=False):
    ec2 = s.client("ec2")
    now = dt.datetime.now(dt.timezone.utc)
    for i in lab_instances(ec2):
        deadline = tag(i, "deadline")
        late = not deadline or dt.datetime.fromisoformat(deadline) < now
        if late or i["State"]["Name"] in ("stopped", "stopping"):
            print("sweep: terminating", i["InstanceId"], "(deadline", deadline or "missing", ")")
            ec2.terminate_instances(InstanceIds=[i["InstanceId"]])
        elif not quiet:
            print("sweep: within its deadline:", i["InstanceId"])


def cmd_up(s, itype: str, minutes: int):
    if itype not in ALLOWED:
        sys.exit(f"refusing: only {sorted(ALLOWED)} may be started")
    if not (10 <= minutes <= MAX_MINUTES_CAP):
        sys.exit(f"refusing: minutes must be 10..{MAX_MINUTES_CAP}")
    ec2 = s.client("ec2")
    cmd_sweep(s, quiet=True)
    if lab_instances(ec2):
        sys.exit("refusing: a lab instance already exists (see status); only one at a time")
    print(f"worst case for this session: ${worst_case_usd(itype, minutes)} ({itype}, {minutes} min + {BACKSTOP_GRACE_MIN} min grace, {DISK_GB} GB disk)")
    ensure_roles(s)
    sg = ensure_sg(ec2)
    ami = s.client("ssm").get_parameter(Name=AMI_PARAM)["Parameter"]["Value"]
    deadline = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes)
    tags = [TAG, {"Key": "Name", "Value": "videomk-gpu-lab"}, {"Key": "deadline", "Value": deadline.isoformat(timespec="seconds")}]
    r = ec2.run_instances(
        ImageId=ami, InstanceType=itype, MinCount=1, MaxCount=1, SecurityGroupIds=[sg], IamInstanceProfile={"Name": PROFILE_NAME},
        InstanceInitiatedShutdownBehavior="terminate", UserData=user_data(minutes),
        MetadataOptions={"HttpTokens": "required", "HttpEndpoint": "enabled"},
        BlockDeviceMappings=[{"DeviceName": "/dev/sda1", "Ebs": {"VolumeSize": DISK_GB, "VolumeType": "gp3", "DeleteOnTermination": True, "Encrypted": True}}],
        TagSpecifications=[{"ResourceType": "instance", "Tags": tags}, {"ResourceType": "volume", "Tags": [TAG]}])
    iid = r["Instances"][0]["InstanceId"]
    try:   # the outside backstop: created immediately; if it cannot be created, the instance does not get to live
        fire = deadline + dt.timedelta(minutes=BACKSTOP_GRACE_MIN)
        role_arn = f"arn:aws:iam::{ACCOUNT}:role/{SCHED_ROLE}"
        for attempt in range(6):
            try:
                s.client("scheduler").create_schedule(
                    Name=backstop_name(iid), ScheduleExpression=f"at({fire.strftime('%Y-%m-%dT%H:%M:%S')})", ScheduleExpressionTimezone="UTC",
                    FlexibleTimeWindow={"Mode": "OFF"}, ActionAfterCompletion="DELETE",
                    Target={"Arn": "arn:aws:scheduler:::aws-sdk:ec2:terminateInstances", "RoleArn": role_arn, "Input": json.dumps({"InstanceIds": [iid]})})
                break
            except Exception as e:   # a freshly created role can take a few seconds to be assumable
                if attempt == 5:
                    raise
                time.sleep(6)
    except Exception as e:
        ec2.terminate_instances(InstanceIds=[iid])
        sys.exit(f"backstop could not be created ({type(e).__name__}: {e}); the instance was terminated")
    print("started", iid, "deadline", deadline.isoformat(timespec="seconds"), "backstop at", fire.isoformat(timespec="seconds"))


def cmd_status(s):
    ec2 = s.client("ec2")
    now = dt.datetime.now(dt.timezone.utc)
    insts = lab_instances(ec2)
    if not insts:
        print("no lab instance exists")
    for i in insts:
        age_h = (now - i["LaunchTime"]).total_seconds() / 3600
        dl = tag(i, "deadline")
        left = (dt.datetime.fromisoformat(dl) - now).total_seconds() / 60 if dl else float("nan")
        print(f"{i['InstanceId']} {i['InstanceType']} {i['State']['Name']} age {age_h * 60:.0f} min, {left:.0f} min left, about ${ALLOWED.get(i['InstanceType'], 2) * age_h:.2f} so far")
        try:
            sc = s.client("scheduler").get_schedule(Name=backstop_name(i["InstanceId"]))
            print("  backstop:", sc["ScheduleExpression"], sc["State"])
        except Exception as e:
            print("  BACKSTOP MISSING:", type(e).__name__)


def cmd_down(s):
    ec2 = s.client("ec2")
    for i in lab_instances(ec2):
        ec2.terminate_instances(InstanceIds=[i["InstanceId"]])
        print("terminated", i["InstanceId"])
        try:
            s.client("scheduler").delete_schedule(Name=backstop_name(i["InstanceId"]))
        except Exception:
            pass


def cmd_run(s, command: str, timeout: int):
    ec2, ssm = s.client("ec2"), s.client("ssm")
    insts = lab_instances(ec2, states=("running",))
    if not insts:
        sys.exit("no running lab instance")
    iid = insts[0]["InstanceId"]
    wrapped = "sudo -u ubuntu -H bash -lc " + json.dumps("cd /lab && " + command)
    cid = ssm.send_command(InstanceIds=[iid], DocumentName="AWS-RunShellScript", TimeoutSeconds=min(timeout, 14400),
                           Parameters={"commands": [wrapped], "executionTimeout": [str(timeout)]})["Command"]["CommandId"]
    while True:
        time.sleep(4)
        try:
            inv = ssm.get_command_invocation(CommandId=cid, InstanceId=iid)
        except ssm.exceptions.InvocationDoesNotExist:
            continue
        if inv["Status"] not in ("Pending", "InProgress", "Delayed"):
            break
    print(inv["StandardOutputContent"][-6000:])
    if inv["StandardErrorContent"].strip():
        print("--- stderr ---\n" + inv["StandardErrorContent"][-3000:])
    print(f"[{inv['Status']} exit {inv.get('ResponseCode')}]")
    sys.exit(0 if inv["Status"] == "Success" else 1)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    up = sub.add_parser("up"); up.add_argument("--type", default="g6.xlarge"); up.add_argument("--minutes", type=int, default=DEFAULT_MINUTES)
    run = sub.add_parser("run"); run.add_argument("command"); run.add_argument("--timeout", type=int, default=3600)
    for n in ("status", "down", "sweep"):
        sub.add_parser(n)
    a = ap.parse_args()
    s = session()
    {"up": lambda: cmd_up(s, a.type, a.minutes), "status": lambda: cmd_status(s), "down": lambda: cmd_down(s), "sweep": lambda: cmd_sweep(s),
     "run": lambda: cmd_run(s, a.command, a.timeout)}[a.cmd]()


if __name__ == "__main__":
    main()
