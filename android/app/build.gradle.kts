plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.brillomusical"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.brillomusical"
        minSdk = 26
        targetSdk = 35
        // CI numera cada build para que Android acepte la actualización encima
        versionCode = System.getenv("GITHUB_RUN_NUMBER")?.toInt() ?: 1
        versionName = "0.2.${System.getenv("GITHUB_RUN_NUMBER") ?: "0"}"
    }
    // shortcut: clave en el repo (decisión del usuario), mover a GitHub Secrets si la app se publica
    signingConfigs {
        create("brillo") {
            storeFile = file("brillo.keystore")
            storePassword = "brillomusical"
            keyAlias = "brillo"
            keyPassword = "brillomusical"
        }
    }
    buildTypes {
        getByName("debug") { signingConfig = signingConfigs.getByName("brillo") }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    testImplementation("junit:junit:4.13.2")
}
