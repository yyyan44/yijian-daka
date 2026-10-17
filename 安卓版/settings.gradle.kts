// 一键打卡 · 安卓壳工程（零第三方依赖：只用 AGP，不引 AndroidX / 不引 Kotlin 插件）
pluginManagement {
    repositories {
        gradlePluginPortal()
        google()
        mavenCentral()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "yijian-daka"
include(":app")
