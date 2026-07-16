# deploy/terraform/outputs.tf

output "alb_dns_name" {
  description = "Point your DNS / CloudFront origin at this"
  value       = aws_lb.backend.dns_name
}

output "ecr_backend_repo_url" {
  value = aws_ecr_repository.backend.repository_url
}

output "ecr_web_repo_url" {
  value = aws_ecr_repository.web.repository_url
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "ecs_service_name" {
  value = aws_ecs_service.backend.name
}

output "efs_file_system_id" {
  value = aws_efs_file_system.storage.id
}
