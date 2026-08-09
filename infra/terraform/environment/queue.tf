resource "aws_sqs_queue" "notifications_dlq" {
  for_each                  = local.environments
  name                      = "${var.project_name}-${each.key}-notifications-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "notifications" {
  for_each                   = local.environments
  name                       = "${var.project_name}-${each.key}-notifications"
  visibility_timeout_seconds = 60
  message_retention_seconds  = 345600
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.notifications_dlq[each.key].arn
    maxReceiveCount     = 5
  })
}

resource "aws_sqs_queue_redrive_allow_policy" "notifications" {
  for_each  = local.environments
  queue_url = aws_sqs_queue.notifications_dlq[each.key].id
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.notifications[each.key].arn]
  })
}

data "aws_iam_policy_document" "notification_queue" {
  for_each = local.environments
  statement {
    actions = [
      "sqs:ChangeMessageVisibility",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:ReceiveMessage",
      "sqs:SendMessage",
    ]
    resources = [aws_sqs_queue.notifications[each.key].arn]
  }
}

resource "aws_iam_role_policy" "notification_queue" {
  for_each = local.environments
  name     = "notification-queue-${each.key}"
  role     = aws_iam_role.application[each.key].id
  policy   = data.aws_iam_policy_document.notification_queue[each.key].json
}
