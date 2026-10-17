plugins {
    id("com.android.application")
}

android {
    namespace = "com.yyyan44.daka"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.yyyan44.daka"
        minSdk = 26
        targetSdk = 35
        versionCode = 2
        versionName = "1.1.0"
    }

    // 签名用的 keystore 也放在工程里（默认那个在 ~/.android 下，这个环境写不进去）
    signingConfigs {
        create("local") {
            storeFile = rootProject.file("daka-debug.keystore")
            storePassword = "android"
            keyAlias = "androiddebugkey"
            keyPassword = "android"
        }
    }

    buildTypes {
        getByName("debug") {
            signingConfig = signingConfigs.getByName("local")
        }
        getByName("release") {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("local")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    // 界面就是 assets 里的网页，不引任何第三方库
}
