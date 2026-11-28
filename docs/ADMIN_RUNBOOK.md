# Owner console: runbook (one page)

The console is never the only way. Everything it does is one command from any computer with your AWS credentials. Design: `docs/ADMIN_CONSOLE_DESIGN_2026-11-28.md`. Code: `backend/admin_stack.py`, `backend/admin_console/`.

## QA values (stack `videomk-admin-qa`, account 552357225438, eu-west-1, profile `qa`)

| What | Value |
|---|---|
| Console address | https://d1aoqi2jnahm8s.cloudfront.net |
| Admin pool | `eu-west-1_zipW5vzZq` |
| Flags table (holds the switches) | `videomk-qa-AccountFlagsTable301BEDF5-LYZ987OY1EQ7` |
| Rollup job | `videomk-admin-qa-rollup` |
| Audit bucket | `videomk-admin-qa-audit3d8ade0a-n2j7lkdjax84` |
| Alert topic | `arn:aws:sns:eu-west-1:552357225438:videomk-admin-qa-Alerts91F83244-9MJygRYrPELN` |

Any of them again: `aws cloudformation describe-stacks --stack-name videomk-admin-qa --query "Stacks[0].Outputs" --profile qa --region eu-west-1`. The commands below are written for QA; for another stage change the names.

```
P="--profile qa --region eu-west-1"
FLAGS=videomk-qa-AccountFlagsTable301BEDF5-LYZ987OY1EQ7
POOL=eu-west-1_zipW5vzZq
```

## 1. Emergencies, cheapest harm first

**See the switches**
```
aws dynamodb get-item $P --table-name $FLAGS --key '{"user_id":{"S":"ops:switches"}}'
```
No item, or a field that is not exactly `true`, means "running".

**Stop free videos** (free credits cannot be spent; paid credits work). Live within a minute.
```
aws dynamodb update-item $P --table-name $FLAGS --key '{"user_id":{"S":"ops:switches"}}' \
  --update-expression "SET stop_free_videos = :v, updated_at = :t, updated_by = :b" \
  --expression-attribute-values '{":v":{"BOOL":true},":t":{"S":"'$(date -u +%FT%TZ)'"},":b":{"S":"cli"}}'
```
Back on: the same command with `{"BOOL":false}`. The older way still works too: `python backend/scripts/plans_admin.py config set free_daily_budget_credits 0 --stage qa`, or `gallery-only on`.

**Stop all new videos** (generate and "Try again" answer "VideoMK is briefly paused for maintenance"; videos being made finish; watching, the library, sign-in, cancel and delete keep working).
```
aws dynamodb update-item $P --table-name $FLAGS --key '{"user_id":{"S":"ops:switches"}}' \
  --update-expression "SET stop_new_videos = :v, updated_at = :t, updated_by = :b" \
  --expression-attribute-values '{":v":{"BOOL":true},":t":{"S":"'$(date -u +%FT%TZ)'"},":b":{"S":"cli"}}'
```
Back on: `{"BOOL":false}`. Your own sentence instead of the standard one (optional, both languages): add `message_en = :e, message_es = :s` to the same command.

**Stop paid dictation** (speech to text for Pro and Max: the microphone answers as switched off; typing and everything else keep working). Also a console switch ("Dictation"). Live within a minute.
```
aws dynamodb update-item $P --table-name $FLAGS --key '{"user_id":{"S":"ops:switches"}}' \
  --update-expression "SET stop_dictation = :v, updated_at = :t, updated_by = :b" \
  --expression-attribute-values '{":v":{"BOOL":true},":t":{"S":"'$(date -u +%FT%TZ)'"},":b":{"S":"cli"}}'
```
Back on: `{"BOOL":false}`.

**Suspend one account**: `python backend/scripts/safety_admin.py hold <email or id>` / `clear` (unchanged; the console does not do this yet).

**Stop one video that is stuck**
```
aws stepfunctions list-executions $P --state-machine-arn arn:aws:states:eu-west-1:552357225438:stateMachine:generate_video_workflow_v2 --status-filter RUNNING
aws stepfunctions stop-execution $P --execution-arn <arn from the list>
```

## 2. The console itself

**Lock the console now** (lost phone, a sign-in email you did not cause). Sessions already open end within 10 minutes.
```
aws cognito-idp list-users $P --user-pool-id $POOL --query "Users[].Username"
aws cognito-idp admin-disable-user $P --user-pool-id $POOL --username <name from the list>
aws cognito-idp admin-user-global-sign-out $P --user-pool-id $POOL --username <name>
```
Open it again: `admin-enable-user`.

**Locked out** (lost passkey AND lost password or authenticator). Start again from zero:
```
aws cognito-idp admin-delete-user $P --user-pool-id $POOL --username <name>
aws cognito-idp admin-create-user $P --user-pool-id $POOL --username hello@videomk.com \
  --user-attributes Name=email,Value=hello@videomk.com Name=email_verified,Value=true --desired-delivery-mediums EMAIL
```
The pool emails a temporary password (valid 3 days) to that address; then follow "First sign-in" below. Never pass `--temporary-password` on the command line: it would sit in your shell history.
The invitation expired before you used it: the same `admin-create-user` command with `--message-action RESEND`.

**Remove a passkey** (a phone you no longer have): sign in, or with the command line there is no direct command; delete and re-create the user as above.

**Travelling** (the console is served only to the countries in the list; elsewhere it answers 403):
```
aws cloudformation update-stack $P --stack-name videomk-admin-qa --use-previous-template --capabilities CAPABILITY_IAM \
  --parameters ParameterKey=AllowedCountries,ParameterValue='GB\,ES\,FR' ParameterKey=BootstrapVersion,UsePreviousValue=true
```
It takes a few minutes. The switches of section 1 never depend on it.

**The numbers are old / "rollup stopped" alarm**
```
aws lambda invoke $P --function-name videomk-admin-qa-rollup /dev/stdout          # run it now; prints what it counted
aws logs tail $P /aws/lambda/videomk-admin-qa-rollup --since 3h
```
**Test that alert emails arrive**: `aws lambda invoke $P --function-name videomk-admin-qa-rollup --cli-binary-format raw-in-base64-out --payload '{"test_alert":true}' /dev/stdout`

**Read the audit log** (every sign-in and every switch; entries cannot be changed or deleted for 400 days, by anyone):
```
aws s3 ls $P s3://videomk-admin-qa-audit3d8ade0a-n2j7lkdjax84/audit/ --recursive | tail -20
aws s3 cp $P s3://videomk-admin-qa-audit3d8ade0a-n2j7lkdjax84/audit/<key> -
```

**Remove the console entirely**: `cdk destroy videomk-admin-qa -c admin=1 -c stage=qa`. The product is untouched (the console owns no customer data). The audit bucket stays (locked), and the switches stay as they were: set them with section 1.

## 3. First sign-in (once)

1. In the mailbox of hello@videomk.com: confirm the alert subscription ("AWS Notification - Subscription Confirmation", link "Confirm subscription"). Until then no alert email arrives.
2. Find the email "VideoMK console: your first sign-in": it has the sign-in name and a temporary password (3 days).
3. On the phone, in Safari, type the console address yourself (do not follow a link). Tap "Recovery or first sign-in", enter the name and the temporary password.
4. "Choose your recovery password": the page proposes a 40-character one. Save it OFF the phone (password manager on the computer, or paper), then continue.
5. "Add your authenticator app": add the key to an authenticator app (best on another device), type the 6-digit code.
6. "Add a passkey": tap, confirm with Face ID. From now on: open the address, "Sign in with passkey", Face ID.
7. Recommended on the iPhone: Settings, Face ID and Passcode, Stolen Device Protection on.

## 4. Deploy

```
cd backend && scripts/admin_console.sh qa diff      # then: deploy
```
Only ever touches `videomk-admin-<stage>`. The main stack needs the day index (`GSI_UsageDay`) and the launcher's switch hook: deployed with the usual `scripts/deploy.sh`. Until the index exists the rollup job reads the same small fields with a scan (the page says so).
A new stage: deploy once, put the stack output `ConsoleHost` in `stages.json` as `adminHost`, deploy again (the passkey is bound to the address), then create the user (section 2, "Locked out", the second command).

## 5. Alerts and thresholds

| Alert | Fires when | Judged by |
|---|---|---|
| videos are failing | 3 or more failures among the videos started in the last hour AND more than 20 % of that hour's finished videos | rollup job, hourly |
| a video is stuck | a run still going after 30 minutes | rollup job, hourly |
| free budget at 80 % / 100 % | of the day's free credits (`free_daily_budget_credits`) | rollup job, hourly |
| console sign-in | every sign-in | at once |
| switch used | every change from the console | at once |
| rollup stopped | no finished run for 2 hours | alarm `videomk-admin-qa-rollup-stopped` |
| rollup errors, console errors | a function raised an error | alarms |
| any alarm of the main stack (`videomk-qa-...`: account deletion, free spend) | ALARM or back to OK | forwarded by an EventBridge rule |

Thresholds are variables of the rollup function (`ALERT_FAIL_MIN`, `ALERT_FAIL_SHARE`, `ALERT_STUCK_MINUTES`). A change made with the command line (section 1) is not emailed: only console changes are.
