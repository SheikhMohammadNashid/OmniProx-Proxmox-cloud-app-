pipeline {
    agent any
    environment {
        DOCKER_USER = "sheikhnashid"
        STG_USER = "stg"
        PROD_USER = "prod"
        STAGING_IP = "192.168.0.179"
        PROD_IP = "192.168.0.161"
        DOCKER_CREDS_ID = "docker-hub-creds"
        SSH_CREDS_ID = "vm-deploy-key"
        TAG = "${env.BUILD_NUMBER}"
    }
    stages {
        stage('Build & Push') {
            steps {
                script {
                    withCredentials([usernamePassword(credentialsId: DOCKER_CREDS_ID, passwordVariable: 'PASS', usernameVariable: 'USER')]) {
                        sh "echo \$PASS | docker login -u \$USER --password-stdin"

                        // Build & Push single app image
                        sh "docker build -t ${DOCKER_USER}/omniprox:v${TAG} ." 
                        sh "docker push ${DOCKER_USER}/omniprox:v${TAG}"
                    }
                }
            }
        }
        stage('Deploy to Staging') {
            steps {
                sshagent([SSH_CREDS_ID]) {
                    sh "scp -o StrictHostKeyChecking=no docker-compose.yml ${STG_USER}@${STAGING_IP}:~/docker-compose.yml"
                    sh """
                        ssh -o StrictHostKeyChecking=no ${STG_USER}@${STAGING_IP} '
                            docker ps -a --format "{{.Names}}" | grep -E "^omniprox" | xargs -r docker rm -f
                            export TAG=${TAG}
                            export DOCKER_USER=${DOCKER_USER}
                            docker compose up -d
                        '
                    """
                }
            }
        }
        stage('Approval Gate') {
            steps {
                input message: "Verify Staging at http://${STAGING_IP}:8000. Promote to Production?", ok: "Deploy!"
            }
        }
        stage('Deploy to Production') {
            steps {
                sshagent([SSH_CREDS_ID]) {
                    sh "scp -o StrictHostKeyChecking=no docker-compose.yml ${PROD_USER}@${PROD_IP}:~/docker-compose.yml"
                    sh """
                        ssh -o StrictHostKeyChecking=no ${PROD_USER}@${PROD_IP} '
                            docker ps -a --format "{{.Names}}" | grep -E "^docmind-rag" | xargs -r docker rm -f
                            export TAG=${TAG}
                            export DOCKER_USER=${DOCKER_USER}
                            docker compose pull
                            docker compose up -d --remove-orphans
                        '
                    """
                }
            }
        }
    }
}
