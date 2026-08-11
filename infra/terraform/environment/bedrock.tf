data "aws_iam_policy_document" "bedrock" {
  for_each = local.environments
  statement {
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = [
      "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.bedrock_model_id}",
    ]
  }
}

resource "aws_iam_role_policy" "bedrock" {
  for_each = local.environments
  name     = "bedrock-${each.key}"
  role     = aws_iam_role.application[each.key].id
  policy   = data.aws_iam_policy_document.bedrock[each.key].json
}
