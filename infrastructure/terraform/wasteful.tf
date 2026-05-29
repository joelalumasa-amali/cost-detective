# Unattached EBS volume
resource "aws_ebs_volume" "wasteful" {
  availability_zone = "eu-west-1a"
  size              = 50
  type              = "gp2"

  tags = {
    Name = "${var.project_name}-wasteful-volume"
  }
}

# Unassociated Elastic IP
resource "aws_eip" "wasteful" {
  domain = "vpc"

  tags = {
    Name = "${var.project_name}-wasteful-eip"
  }
}

# Idle large EC2 instance (no workload)
resource "aws_instance" "wasteful" {
  ami           = "ami-0720a3ca2735bf2fa"
  instance_type = "t3.large"

  tags = {
    Name = "${var.project_name}-idle-instance"
  }
}
