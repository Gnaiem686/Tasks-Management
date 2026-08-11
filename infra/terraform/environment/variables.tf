variable "project_name" {
  type    = string
  default = "workforce-risk"
}

variable "environment" {
  description = "Shared cluster scope; dev and prod are namespaces, not separate clusters."
  type        = string
  default     = "shared"
  validation {
    condition     = var.environment == "shared"
    error_message = "The approved topology has one shared cluster; use shared."
  }
}

variable "aws_region" {
  type = string
}

variable "vpc_cidr" {
  type    = string
  default = "10.40.0.0/16"
}

variable "admin_cidr" {
  description = "Trusted administration CIDR; never use a world-open CIDR."
  type        = string
  validation {
    condition     = var.admin_cidr != "0.0.0.0/0" && var.admin_cidr != "::/0"
    error_message = "admin_cidr must be a restricted trusted network."
  }
}

variable "kubernetes_version" {
  description = "Exact Kubernetes minor package channel, for example 1.34."
  type        = string
  validation {
    condition     = can(regex("^[0-9]+\\.[0-9]+$", var.kubernetes_version))
    error_message = "Use an exact major.minor Kubernetes channel."
  }
}

variable "kubernetes_package_version" {
  description = "Exact kubelet/kubeadm/kubectl apt version."
  type        = string
  validation {
    condition     = can(regex("^[0-9]+\\.[0-9]+\\.[0-9]+-[0-9.]+$", var.kubernetes_package_version))
    error_message = "Use an exact Kubernetes package version."
  }
}

variable "containerd_version" {
  description = "Exact Ubuntu containerd apt package version."
  type        = string
  validation {
    condition     = length(var.containerd_version) > 5 && !strcontains(var.containerd_version, "latest")
    error_message = "Use an exact containerd package version."
  }
}

variable "calico_version" {
  description = "Exact Calico release used by control-plane bootstrap."
  type        = string
  validation {
    condition     = can(regex("^v[0-9]+\\.[0-9]+\\.[0-9]+$", var.calico_version))
    error_message = "Use an exact vX.Y.Z Calico version."
  }
}

variable "control_plane_instance_type" {
  type    = string
  default = "t3.medium"
}

variable "worker_instance_type" {
  type    = string
  default = "t3.medium"
}

variable "join_token_ttl" {
  type    = string
  default = "30m"
}

variable "node_generation" {
  description = "Increment only when deliberately replacing cluster nodes."
  type        = number
  default     = 1
}

variable "dev_database_name" {
  type    = string
  default = "workforce_dev"
}

variable "prod_database_name" {
  type    = string
  default = "workforce_prod"
}

variable "postgres_engine_version" {
  description = "Reviewed exact RDS PostgreSQL engine version."
  type        = string
}

variable "rds_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "bedrock_model_id" {
  description = "Phase 0 validated Bedrock foundation model ID."
  type        = string
}

variable "ses_identity_arn" {
  description = "Verified SES domain or email identity ARN; verification is an external gate."
  type        = string
}
