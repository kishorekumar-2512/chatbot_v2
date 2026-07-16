# deploy/terraform/variables.tf
#
# This Terraform provisions the APPLICATION layer only (ECR, ECS, ALB, EFS,
# IAM, CloudWatch) — it assumes your VPC and RDS instance already exist as
# company-managed resources, referenced here by ID rather than created here.
# Provisioning the network/database layer blind, with no way to actually
# run `terraform plan` against your real AWS account from here, is a much
# higher-risk thing to hand you pre-written than the app layer is — fill in
# your real VPC/subnet/RDS values below and run `terraform validate` and
# `terraform plan` yourself before `apply`.

variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "project_name" {
  type    = string
  default = "chatbot"
}

variable "vpc_id" {
  description = "Existing VPC ID"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for ECS tasks and EFS mount targets (needs NAT/VPC endpoints for ECR, Secrets Manager, etc.)"
  type        = list(string)
}

variable "public_subnet_ids" {
  description = "Public subnet IDs for the ALB"
  type        = list(string)
}

variable "rds_security_group_id" {
  description = "Security group attached to your existing RDS instance — the ECS task SG will be granted ingress to it on 5432"
  type        = string
}

variable "container_cpu" {
  type    = number
  default = 1024
}

variable "container_memory" {
  type    = number
  default = 3072
}

variable "desired_count" {
  description = "Number of backend tasks — start at 2 for basic HA once this is used company-wide, not 1"
  type        = number
  default     = 2
}

variable "acm_certificate_arn" {
  description = "ACM cert ARN for HTTPS on the ALB — leave empty to deploy HTTP-only initially (not recommended for real use)"
  type        = string
  default     = ""
}

variable "secret_arns" {
  description = "Secrets Manager ARNs the task needs to read (DATABASE_URL, GROQ_API_KEY, GEMINI_API_KEY, ADMIN_API_KEY)"
  type        = map(string)
}

variable "backend_image" {
  description = "Full ECR image URI (set by CI after pushing) — e.g. ACCOUNT.dkr.ecr.REGION.amazonaws.com/chatbot-backend:TAG"
  type        = string
  default     = ""
}

variable "frontend_domain_aliases" {
  description = "Custom domain names for the CloudFront distribution (e.g. ['chat.example.com']). Leave empty to use the default CloudFront URL."
  type        = list(string)
  default     = []
}
