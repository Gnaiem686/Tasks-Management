variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "github_repository" {
  type    = string
  default = "Gnaiem686/Tasks-Management"
}

variable "github_repository_subject" {
  description = "Stable GitHub OIDC owner and repository subject, including numeric IDs"
  type        = string
  default     = "Gnaiem686@200245854/Tasks-Management@1310142094"
}

variable "project_name" {
  type    = string
  default = "workforce-risk"
}
