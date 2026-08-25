output "state_backend" {
  description = "Sensitive backend bootstrap values supplied to later init commands."
  sensitive   = true
  value = {
    bucket          = aws_s3_bucket.terraform_state.id
    kms_key_id      = aws_kms_key.terraform_state.arn
    lock_table      = aws_dynamodb_table.terraform_locks.name
    use_lockfile    = true
    shared_key      = "shared/terraform.tfstate"
    environment_key = "environment/terraform.tfstate"
  }
}
