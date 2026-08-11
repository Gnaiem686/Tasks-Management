resource "aws_security_group" "database" {
  name_prefix = "${var.project_name}-database-"
  vpc_id      = aws_vpc.cluster.id

  ingress {
    description     = "PostgreSQL from Kubernetes nodes only"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.nodes.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
  }
}

resource "aws_db_subnet_group" "application" {
  name       = "${var.project_name}-shared-private"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_db_instance" "application" {
  identifier                  = "${var.project_name}-postgres"
  engine                      = "postgres"
  engine_version              = var.postgres_engine_version
  instance_class              = var.rds_instance_class
  allocated_storage           = 20
  max_allocated_storage       = 100
  storage_type                = "gp3"
  storage_encrypted           = true
  db_name                     = "workforce_admin"
  username                    = "workforce_admin"
  manage_master_user_password = true
  publicly_accessible         = false
  db_subnet_group_name        = aws_db_subnet_group.application.name
  vpc_security_group_ids      = [aws_security_group.database.id]
  backup_retention_period     = 7
  copy_tags_to_snapshot       = true
  deletion_protection         = true
  skip_final_snapshot         = false
  final_snapshot_identifier   = "${var.project_name}-postgres-final"
  apply_immediately           = false

  lifecycle {
    prevent_destroy = true
  }
}
