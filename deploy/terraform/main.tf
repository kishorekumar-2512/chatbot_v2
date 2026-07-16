# deploy/terraform/main.tf

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

provider "aws" {
  region = var.aws_region
}

# ── ECR ────────────────────────────────────────────────────────────────────────
resource "aws_ecr_repository" "backend" {
  name                 = "${var.project_name}-backend"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_repository" "web" {
  name                 = "${var.project_name}-web"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

# ── CloudWatch ────────────────────────────────────────────────────────────────
resource "aws_cloudwatch_log_group" "backend" {
  name              = "/ecs/${var.project_name}-backend"
  retention_in_days = 30
}

# ── Security groups ───────────────────────────────────────────────────────────
resource "aws_security_group" "alb" {
  name        = "${var.project_name}-alb-sg"
  description = "Allow inbound HTTP/HTTPS from company network"
  vpc_id      = var.vpc_id

  ingress {
    from_port = 80
    to_port   = 80
    protocol  = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # tighten to your company CIDR/VPN range in production
  }
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "ecs_tasks" {
  name        = "${var.project_name}-ecs-tasks-sg"
  description = "Backend ECS tasks — inbound only from the ALB"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "efs" {
  name        = "${var.project_name}-efs-sg"
  description = "EFS mount targets — NFS from ECS tasks only"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 2049
    to_port         = 2049
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_tasks.id]
  }
}

# Grant the backend's SG ingress on the EXISTING RDS security group — this
# resource lives here because it modifies a resource you own outside this
# module (your RDS SG); review before applying if your RDS SG is managed
# by a different Terraform state.
resource "aws_security_group_rule" "rds_ingress_from_backend" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = var.rds_security_group_id
  source_security_group_id = aws_security_group.ecs_tasks.id
}

# ── EFS (persistent ChromaDB index + key store, survives task restarts) ────────
resource "aws_efs_file_system" "storage" {
  creation_token = "${var.project_name}-storage"
  encrypted      = true
  tags           = { Name = "${var.project_name}-storage" }
}

resource "aws_efs_mount_target" "storage" {
  for_each        = toset(var.private_subnet_ids)
  file_system_id  = aws_efs_file_system.storage.id
  subnet_id       = each.value
  security_groups = [aws_security_group.efs.id]
}

resource "aws_efs_access_point" "chroma_index" {
  file_system_id = aws_efs_file_system.storage.id
  posix_user   { uid = 1000, gid = 1000 }
  root_directory {
    path = "/chroma-index"
    creation_info { owner_uid = 1000, owner_gid = 1000, permissions = "755" }
  }
}

resource "aws_efs_access_point" "key_store" {
  file_system_id = aws_efs_file_system.storage.id
  posix_user   { uid = 1000, gid = 1000 }
  root_directory {
    path = "/key-store"
    creation_info { owner_uid = 1000, owner_gid = 1000, permissions = "755" }
  }
}

# ── IAM ────────────────────────────────────────────────────────────────────────
data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${var.project_name}-ecs-execution-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Execution role also needs to read the Secrets Manager secrets referenced
# in the task definition's `secrets` block (this is separate from the task
# role — execution role permissions apply at container startup).
data "aws_iam_policy_document" "read_secrets" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = values(var.secret_arns)
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  name   = "${var.project_name}-read-secrets"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.read_secrets.json
}

resource "aws_iam_role" "task" {
  name               = "${var.project_name}-ecs-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

data "aws_iam_policy_document" "efs_access" {
  statement {
    actions = ["elasticfilesystem:ClientMount", "elasticfilesystem:ClientWrite"]
    resources = [aws_efs_file_system.storage.arn]
  }
}

resource "aws_iam_role_policy" "task_efs" {
  name   = "${var.project_name}-efs-access"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.efs_access.json
}

# ── ALB ────────────────────────────────────────────────────────────────────────
resource "aws_lb" "backend" {
  name               = "${var.project_name}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.public_subnet_ids
}

resource "aws_lb_target_group" "backend" {
  name        = "${var.project_name}-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
    timeout             = 5
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.backend.arn
  port              = 80
  protocol          = "HTTP"

  # Redirects to HTTPS once you've supplied a cert; serves the app directly
  # over HTTP until then so this is usable before you've set up ACM.
  dynamic "default_action" {
    for_each = var.acm_certificate_arn == "" ? [1] : []
    content {
      type             = "forward"
      target_group_arn = aws_lb_target_group.backend.arn
    }
  }
  dynamic "default_action" {
    for_each = var.acm_certificate_arn == "" ? [] : [1]
    content {
      type = "redirect"
      redirect { port = "443", protocol = "HTTPS", status_code = "HTTP_301" }
    }
  }
}

resource "aws_lb_listener" "https" {
  count             = var.acm_certificate_arn == "" ? 0 : 1
  load_balancer_arn = aws_lb.backend.arn
  port              = 443
  protocol          = "HTTPS"
  certificate_arn   = var.acm_certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }
}

# ── ECS ────────────────────────────────────────────────────────────────────────
resource "aws_ecs_cluster" "this" {
  name = "${var.project_name}-cluster"
}

resource "aws_ecs_task_definition" "backend" {
  family                   = "${var.project_name}-backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.container_cpu
  memory                   = var.container_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name      = "backend"
    image     = var.backend_image
    essential = true
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]
    environment = [
      { name = "PRIMARY_LLM", value = "groq" },
      { name = "GROQ_MODEL", value = "openai/gpt-oss-120b" },
      { name = "GEMINI_MODEL", value = "gemini-3.1-flash-lite" },
      { name = "RETRIEVAL_TOP_K", value = "8" },
      { name = "REINDEX_INTERVAL_HOURS", value = "24" },
      { name = "CHROMA_DB_PATH", value = "/app/embeddings/chroma_store" },
      { name = "KEY_STORE_PATH", value = "/app/data/llm_keys.json" },
      { name = "DB_SSL_MODE", value = "require" },
    ]
    secrets = [
      { name = "DATABASE_URL", valueFrom = var.secret_arns["database_url"] },
      { name = "GROQ_API_KEY", valueFrom = var.secret_arns["groq_api_key"] },
      { name = "GEMINI_API_KEY", valueFrom = var.secret_arns["gemini_api_key"] },
      { name = "ADMIN_API_KEY", valueFrom = var.secret_arns["admin_api_key"] },
    ]
    mountPoints = [
      { sourceVolume = "chroma-index", containerPath = "/app/embeddings/chroma_store", readOnly = false },
      { sourceVolume = "key-store", containerPath = "/app/data", readOnly = false },
    ]
    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 30
    }
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.backend.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "backend"
      }
    }
  }])

  volume {
    name = "chroma-index"
    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.storage.id
      transit_encryption = "ENABLED"
      authorization_config {
        access_point_id = aws_efs_access_point.chroma_index.id
        iam             = "ENABLED"
      }
    }
  }
  volume {
    name = "key-store"
    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.storage.id
      transit_encryption = "ENABLED"
      authorization_config {
        access_point_id = aws_efs_access_point.key_store.id
        iam             = "ENABLED"
      }
    }
  }
}

resource "aws_ecs_service" "backend" {
  name            = "${var.project_name}-backend"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name    = "backend"
    container_port    = 8000
  }

  depends_on = [aws_lb_listener.http]
}
