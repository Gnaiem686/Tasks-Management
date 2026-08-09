output "release_foundation" {
  sensitive = true
  value = {
    role_arns       = { for environment, role in aws_iam_role.github_environment : environment => role.arn }
    repository_urls = { for service, repository in aws_ecr_repository.application : service => repository.repository_url }
    account_id      = data.aws_caller_identity.current.account_id
  }
}
