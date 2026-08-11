variable "aws_region" {
  description = "AWS region that owns the Terraform state foundation."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Stable project identifier used in resource names and tags."
  type        = string
  default     = "workforce-risk"
}

variable "owner" {
  description = "Operational owner tag."
  type        = string
  default     = "workforce-platform"
}
