# SafeSakhi – AI-Powered Women's Safety Platform

SafeSakhi is an AI-driven safety platform that detects potential threats to women's safety using audio, motion, and text analysis powered by AWS serverless technologies.

## Core Features
- Real-time audio threat detection using Amazon Transcribe & Comprehend
- Motion-based threat detection using phone sensors
- Text threat detection via NLP
- Risk scoring and emergency alert system
- Fully serverless architecture using AWS Lambda, DynamoDB, SNS, and S3

## Technologies Used
- **AWS Lambda**: Serverless compute for all backend logic.
- **Amazon DynamoDB**: NoSQL database for storing analysis results, user profiles, risk assessments, and incident history.
- **Amazon S3**: Object storage for temporary audio files and long-term evidence storage.
- **Amazon SNS**: Notification service for sending emergency alerts.
- **Amazon Comprehend**: Natural Language Processing for text and audio sentiment, key phrase, and entity detection.
- **Amazon Transcribe**: Speech-to-text conversion for audio analysis.
- **AWS API Gateway**: Exposing RESTful endpoints for incoming sensor data.
- **AWS Serverless Application Model (SAM)**: For defining and deploying the serverless infrastructure.
- **Python 3.9**: Programming language for all Lambda functions.

## Folder Structure
- `lambdas/` – Source code for all AWS Lambda functions (audio_processor, motion_analyzer, text_analyzer, risk_assessor, emergency_responder)
- `infrastructure/` – Deployment templates (`template.yaml` for SAM) and configuration (`samconfig.toml`)
- `tests/` – Unit and integration tests for each component (placeholder)

## Status
🚧 MVP in progress – core logic complete, frontend and deployment scaffolding underway.

---

## Setup & Local Development

### Prerequisites
- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) configured with appropriate credentials.
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html) installed.
- [Python 3.9+](https://www.python.org/downloads/) installed.
- [Docker](https://docs.docker.com/get-docker/) installed and running (required for `sam build --use-container`).

### Steps
1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/your-username/safesakhi.git](https://github.com/your-username/safesakhi.git)
    cd safesakhi
    ```
2.  **Install Lambda Dependencies:**
    Each Lambda function has its own `requirements.txt` for isolation. Ensure `boto3` is listed in each.
    ```bash
    # Example for one lambda directory
    cd lambdas/audio_processor
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    deactivate
    # Repeat for other lambda directories or use a script to automate
    ```
3.  **Local Environment Variables:**
    Create a `.env` file in your root `infrastructure/` directory (or respective lambda directories if testing locally) and populate it with necessary environment variables as defined in `infrastructure/template.yaml`.
    ```
    # Example for .env (in infrastructure/ directory)
    LOG_LEVEL=DEBUG
    AUDIO_ANALYSIS_TABLE_NAME=SafeSakhi-AudioAnalysis
    MOTION_ANALYSIS_TABLE_NAME=SafeSakhi-MotionAnalysis
    TEXT_ANALYSIS_TABLE_NAME=SafeSakhi-TextAnalysis
    EVIDENCE_TABLE_NAME=SafeSakhi-Evidence
    RISK_ASSESSMENTS_TABLE_NAME=SafeSakhi-RiskAssessments
    USERS_TABLE_NAME=SafeSakhi-Users
    INCIDENT_HISTORY_TABLE_NAME=SafeSakhi-IncidentHistory
    RISK_ASSESSMENT_LAMBDA_NAME=SafeSakhi-RiskAssessment
    EMERGENCY_RESPONSE_LAMBDA_NAME=SafeSakhi-EmergencyResponse
    AUDIO_TEMP_BUCKET_NAME=safesakhi-audio-temp-YOURACCOUNTID
    EVIDENCE_S3_BUCKET_NAME=safesakhi-evidence-store-YOURACCOUNTID
    # ... and so on for all numerical and string based configuration variables from template.yaml
    ```
    *Remember to replace `YOURACCOUNTID` with your actual AWS account ID.*

## Deployment

To deploy the SafeSakhi application to your AWS account:

1.  **Navigate to the Infrastructure Directory:**
    ```bash
    cd infrastructure/
    ```
2.  **Build the SAM application:**
    ```bash
    sam build --use-container
    ```
    * `--use-container`: Highly recommended to ensure dependencies are built in a Lambda-compatible environment.
3.  **Deploy the application:**
    ```bash
    sam deploy --guided
    ```
    Follow the prompts. SAM CLI will guide you through setting up the stack name, AWS region, and confirming IAM capabilities. Select `y` when asked to save arguments to `samconfig.toml`.

## Usage

Once deployed, you can interact with the API Gateway endpoints. Retrieve your API URL from the CloudFormation stack outputs or using `sam outputs`.

### Example API Endpoints:

* **Audio Processor (`POST /audio-input`):** Processes base64-encoded audio.
* **Motion Analyzer (`POST /motion-input`):** Handles motion and location data.
* **Text Analyzer (`POST /text-input`):** Analyzes textual messages.

(For detailed `curl` examples with example JSON payloads, refer to the previous communication or your test scripts.)

---

## Troubleshooting Common Issues

Encountering issues during deployment or runtime is normal. Here are some common problems and how to debug them:

### 1. IAM Permission Problems

* **Symptom:** `AccessDeniedException` errors in CloudWatch logs, or `User: arn:aws:iam::... is not authorized to perform: ...` messages during `sam deploy`.
* **How to debug:**
    * **CloudWatch Logs:** Check the Lambda function's logs for explicit `AccessDenied` messages. They often tell you which specific action (`s3:GetObject`, `dynamodb:PutItem`, etc.) you're missing.
    * **CloudFormation Console:** If `sam deploy` fails, go to the AWS CloudFormation console, find your `SafeSakhiStack`, and check the "Events" tab. Look for `CREATE_FAILED` or `UPDATE_FAILED` events on IAM Roles or Policies.
    * **Review `template.yaml`:** Double-check the `Policies` section for the Lambda function causing the error. Ensure the `Action` and `Resource` are correctly specified.
    * **Least Privilege:** While we've aimed for least privilege, sometimes you might need to temporarily broaden a policy (e.g., `s3:*` on a specific bucket) to confirm it's an IAM issue, then narrow it down again.

### 2. Docker Connectivity Issues (`sam build --use-container`)

* **Symptom:** `Cannot connect to the Docker daemon at ...` or similar Docker-related errors during `sam build`.
* **How to debug:**
    * **Ensure Docker is Running:** Verify that your Docker application (Docker Desktop on Windows/macOS, or Docker daemon on Linux) is running.
    * **Docker Configuration:** Check your Docker configuration to ensure it's accessible from your terminal. Restarting Docker often resolves transient issues.

### 3. CloudFormation Stack Failures

* **Symptom:** `sam deploy` reports `ROLLBACK_COMPLETE` or `CREATE_FAILED` for your stack.
* **How to debug:**
    * **AWS CloudFormation Console:** This is your primary tool.
        1.  Navigate to the AWS CloudFormation service in the console.
        2.  Select your `SafeSakhiStack`.
        3.  Go to the "Events" tab. Scroll up to find the first `FAILED` event. This event's `Status Reason` will usually pinpoint the exact cause (e.g., "BucketAlreadyOwnedByYou" if an S3 bucket name is not unique, or IAM role creation issues).
    * **Logical ID:** The error message often references a "Logical ID" (e.g., `AudioAnalysisTable`). This refers to the resource name in your `template.yaml`.

---

## Performance Monitoring

Monitoring your Lambda functions is key to understanding cost and efficiency.

1.  **CloudWatch Metrics:**
    * Go to AWS Console -> CloudWatch -> Metrics -> Lambda.
    * Select "By Function Name" and choose your `SafeSakhi-*` Lambdas.
    * Monitor metrics like:
        * **Invocations:** How often your functions are called.
        * **Duration:** How long each invocation takes. Long durations can indicate inefficient code or large payloads.
        * **Errors:** Number of invocations that resulted in an error.
        * **Throttles:** If your functions are being rate-limited by AWS.
        * **Memory Utilization:** How much memory your functions are using. Optimize `MemorySize` in `template.yaml` to reduce costs.
    * **Especially for Audio Processing:** Keep a close eye on `AudioProcessorFunction` duration and cost, as Amazon Transcribe and Comprehend can incur significant costs with high usage or large audio files.

2.  **X-Ray Tracing:**
    * Since `Tracing: Active` is enabled in your `Globals` section, you can use AWS X-Ray to visualize the flow of requests through your services.
    * Go to AWS Console -> X-Ray -> Service map. You'll see a map of how your Lambdas, API Gateway, DynamoDB, etc., interact, along with performance details.

---

## Security Testing & Considerations

Beyond basic functionality, consider these security aspects during testing:

1.  **Malformed JSON Payloads:**
    * Test sending invalid JSON to your API Gateway endpoints. API Gateway's default behavior is to return a `400 Bad Request`.
    * Your Lambda functions already have basic validation (`event.get()`, `isinstance`, `len(text.strip()) == 0`). Enhance this with more detailed validation (e.g., JSON Schema validation if using a larger API).

2.  **Very Large Audio/Text Files:**
    * **Lambda Payload Limit (6MB for direct invoke, 10MB for API Gateway request body):** If a user tries to upload an audio file larger than this limit via API Gateway, the request will be rejected before it even reaches Lambda.
    * **Comprehend/Transcribe Limits:** Amazon Transcribe has file size limits (e.g., 2GB for a single audio file for batch jobs). Amazon Comprehend has a 5KB (UTF-8) text size limit for `detect_*` operations. Your `text_analyzer` already handles truncation, but consider how to handle larger inputs for audio (e.g., by uploading directly to S3 and then triggering a batch Transcribe job).
    * **Test Strategy:** Design tests with files just under and just over these limits to confirm behavior. For large audio, the mobile app should upload directly to `safesakhi-audio-temp-YOURACCOUNTID` via a pre-signed URL, and an S3 event (not API Gateway) should trigger `AudioProcessorFunction`.

3.  **Rate Limiting Scenarios:**
    * **API Gateway Throttling:** API Gateway has default throttling limits. Consider setting custom usage plans and API keys if you need to control access rates for different users or applications.
    * **Lambda Concurrency:** Each Lambda function has a default concurrency limit. If invoked too frequently, it might get throttled. Monitor `Throttles` in CloudWatch metrics. You can increase concurrency limits per function if needed (but be mindful of costs).

---

## Production Readiness Checklist

Before deploying to a production environment, review these critical aspects:

1.  **Environment Variable Configuration for Different Stages:**
    * Avoid hardcoding values. You've correctly used environment variables.
    * For multi-stage deployments (dev, staging, prod), use `samconfig.toml` profiles or separate `samconfig.yaml` files.
    * Sensitive values (API keys, Twilio credentials if you integrate for SMS/calls) should be stored securely in AWS Secrets Manager or SSM Parameter Store (SecureString) and retrieved by Lambda at runtime, not directly in `template.yaml` environment variables.

2.  **Encryption Setup for Sensitive Data:**
    * **Data at Rest:**
        * **DynamoDB:** Enable [encryption at rest](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/encryption.html) for all tables. DynamoDB offers AWS owned CMK or customer managed CMK.
        * **S3 Buckets:** Enable [default encryption](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingKMSEncryption.html) for `safesakhi-audio-temp` and `safesakhi-evidence-store`. Consider using a customer-managed KMS key for `safesakhi-evidence-store` as indicated in your `text_analyzer` code.
    * **Data in Transit:** API Gateway and AWS Lambda communicate over HTTPS by default, providing encryption in transit.

3.  **Backup and Disaster Recovery Considerations:**
    * **DynamoDB Point-in-Time Recovery (PITR):** Enable PITR for all DynamoDB tables. This allows continuous backups and recovery to any point in time within the last 35 days.
    * **S3 Versioning:** Enable [versioning](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html) on your S3 buckets, especially `safesakhi-evidence-store`, to protect against accidental deletions or overwrites.
    * **Cross-Region Replication:** For critical data, consider cross-region replication for S3 buckets and DynamoDB global tables for enhanced disaster recovery.

4.  **Monitoring and Alerting:**
    * Set up CloudWatch Alarms on critical metrics (Lambda errors, throttles, high durations, API Gateway 5xx errors).
    * Configure alerts to your team (e.g., via SNS to email, Slack, PagerDuty) if thresholds are breached.

5.  **Cost Management:**
    * Set up AWS Budgets to monitor and alert on projected costs.
    * Regularly review your AWS Cost Explorer to understand spending patterns, especially on services like Transcribe and Comprehend.

6.  **Security Audits and Code Reviews:**
    * Conduct regular security audits of your IAM policies and Lambda code.
    * Implement static code analysis tools (e.g., Bandit for Python) in your CI/CD pipeline.

---
