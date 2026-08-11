data "aws_caller_identity" "current" {}

locals {
  environments = toset(["dev", "prod"])
  database_names = {
    dev  = var.dev_database_name
    prod = var.prod_database_name
  }
  jira_project_scopes = {
    dev  = "WRD"
    prod = "WORKFORCE-PROD"
  }
  environment_release_configuration = {
    for env in local.environments : env => {
      namespace        = env
      database_name    = local.database_names[env]
      jira_project_key = local.jira_project_scopes[env]
    }
  }
  secret_types = toset([
    "database",
    "jira-mcp",
    "api-key-pepper",
    "initial-api-key",
  ])
  secret_containers = {
    for pair in setproduct(local.environments, local.secret_types) :
    "${pair[0]}-${pair[1]}" => {
      environment = pair[0]
      type        = pair[1]
    }
  }
}
