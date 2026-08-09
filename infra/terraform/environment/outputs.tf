output "environment_release_configuration" {
  value     = local.environment_release_configuration
  sensitive = true
}

output "report_bucket_arns" {
  value     = { for env, bucket in aws_s3_bucket.reports : env => bucket.arn }
  sensitive = true
}

output "notification_queue_arns" {
  value     = { for env, queue in aws_sqs_queue.notifications : env => queue.arn }
  sensitive = true
}

output "external_secrets_role_arns" {
  value     = { for env, role in aws_iam_role.external_secrets : env => role.arn }
  sensitive = true
}

output "application_role_arns" {
  value     = { for env, role in aws_iam_role.application : env => role.arn }
  sensitive = true
}

output "rds_endpoint" {
  value     = aws_db_instance.application.endpoint
  sensitive = true
}
