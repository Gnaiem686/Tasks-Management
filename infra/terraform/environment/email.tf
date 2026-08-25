resource "aws_sesv2_configuration_set" "notifications" {
  for_each               = local.environments
  configuration_set_name = "workforce-risk-${each.key}"
  reputation_options { reputation_metrics_enabled = true }
  sending_options { sending_enabled = true }
}

data "aws_iam_policy_document" "email" {
  for_each = local.environments
  statement {
    actions   = ["ses:SendEmail", "ses:SendRawEmail"]
    resources = [var.ses_identity_arn]
    condition {
      test     = "StringEquals"
      variable = "ses:ConfigurationSetName"
      values   = ["workforce-risk-${each.key}"]
    }
  }
}

resource "aws_iam_role_policy" "email" {
  for_each = local.environments
  name     = "email-${each.key}"
  role     = aws_iam_role.application[each.key].id
  policy   = data.aws_iam_policy_document.email[each.key].json
}
