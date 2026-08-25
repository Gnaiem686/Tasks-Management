data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "cluster" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
}

resource "aws_internet_gateway" "cluster" {
  vpc_id = aws_vpc.cluster.id
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.cluster.id
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  map_public_ip_on_launch = false
}

resource "aws_subnet" "private" {
  count                   = 2
  vpc_id                  = aws_vpc.cluster.id
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index + 10)
  map_public_ip_on_launch = false
}

resource "aws_eip" "nat" {
  domain     = "vpc"
  depends_on = [aws_internet_gateway.cluster]
}

resource "aws_nat_gateway" "cluster" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.cluster.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.cluster.id
  }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.cluster.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.cluster.id
  }
}

resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

resource "aws_security_group" "nodes" {
  name_prefix = "${var.project_name}-${var.environment}-nodes-"
  vpc_id      = aws_vpc.cluster.id

  ingress {
    description = "Cluster node-to-node traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    self        = true
  }

  ingress {
    description = "Restricted Kubernetes API administration"
    from_port   = 6443
    to_port     = 6443
    protocol    = "tcp"
    cidr_blocks = [var.admin_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle { create_before_destroy = true }
}

resource "aws_security_group" "ingress_nlb" {
  name_prefix = "${var.project_name}-${var.environment}-ingress-"
  vpc_id      = aws_vpc.cluster.id

  ingress {
    description = "Public HTTP entry point"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Public HTTPS entry point"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 30080
    to_port     = 30443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }
}

resource "aws_security_group_rule" "node_http_from_nlb" {
  type                     = "ingress"
  from_port                = 30080
  to_port                  = 30080
  protocol                 = "tcp"
  security_group_id        = aws_security_group.nodes.id
  source_security_group_id = aws_security_group.ingress_nlb.id
}

resource "aws_security_group_rule" "node_https_from_nlb" {
  type                     = "ingress"
  from_port                = 30443
  to_port                  = 30443
  protocol                 = "tcp"
  security_group_id        = aws_security_group.nodes.id
  source_security_group_id = aws_security_group.ingress_nlb.id
}

resource "aws_lb" "ingress" {
  name               = "workforce-${var.environment}-ingress"
  internal           = false
  load_balancer_type = "network"
  security_groups    = [aws_security_group.ingress_nlb.id]
  subnets            = aws_subnet.public[*].id
}

resource "aws_lb_target_group" "ingress_http" {
  name     = "workforce-${var.environment}-http"
  port     = 30080
  protocol = "TCP"
  vpc_id   = aws_vpc.cluster.id
  health_check {
    protocol = "TCP"
  }
}

resource "aws_lb_target_group" "ingress_https" {
  name     = "workforce-${var.environment}-https"
  port     = 30443
  protocol = "TCP"
  vpc_id   = aws_vpc.cluster.id
  health_check {
    protocol = "TCP"
  }
}

resource "aws_lb_target_group_attachment" "ingress_http" {
  count            = 2
  target_group_arn = aws_lb_target_group.ingress_http.arn
  target_id        = aws_instance.worker[count.index].id
  port             = 30080
}

resource "aws_lb_target_group_attachment" "ingress_https" {
  count            = 2
  target_group_arn = aws_lb_target_group.ingress_https.arn
  target_id        = aws_instance.worker[count.index].id
  port             = 30443
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.ingress.arn
  port              = 80
  protocol          = "TCP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.ingress_http.arn
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.ingress.arn
  port              = 443
  protocol          = "TCP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.ingress_https.arn
  }
}

output "ingress_dns_name" {
  value = aws_lb.ingress.dns_name
}
