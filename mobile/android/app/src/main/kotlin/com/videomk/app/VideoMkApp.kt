package com.videomk.app

import android.app.Application
import com.videomk.app.core.Txt
import com.videomk.app.data.AppLanguage

class VideoMkApp : Application() {
    lateinit var container: AppContainer
        private set
    lateinit var language: AppLanguage
        private set

    override fun onCreate() {
        super.onCreate()
        language = AppLanguage(this)
        language.applyDefault()
        Txt.provider = language.provider()
        container = AppContainer(this)
        container.warmUp()
    }
}
