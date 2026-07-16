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

output "frontend_cloudfront_domain" {
  description = "CloudFront domain name for the React frontend"
  value       = aws_cloudfront_distribution.frontend.domain_name
}

output "frontend_cloudfront_distribution_id" {
  description = "CloudFront distribution ID (needed for cache invalidation in CI/CD)"
  value       = aws_cloudfront_distribution.frontend.id
}

output "frontend_s3_bucket" {
  description = "S3 bucket name for frontend assets"
  value       = aws_s3_bucket.frontend.id
}
