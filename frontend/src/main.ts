import { createPinia } from 'pinia'
import { createApp } from 'vue'
import 'ol/ol.css'

import App from './App.vue'
import router from './router/index'
import './styles/global.less'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.mount('#app')
