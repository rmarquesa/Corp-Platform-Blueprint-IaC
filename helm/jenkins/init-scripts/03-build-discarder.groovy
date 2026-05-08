import jenkins.model.Jenkins
import hudson.tasks.LogRotator

Jenkins.instance.setGlobalBuildDiscarder(
  new LogRotator(30, 10, -1, -1)  // 30 days, 10 builds max
)
Jenkins.instance.save()
