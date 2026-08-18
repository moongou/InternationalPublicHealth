import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import 'maplibre-gl/dist/maplibre-gl.css'
import './styles.css'
import './styles-pages.css'
import './styles-workbench.css'
import './styles-map.css'
import IntranetApp from './IntranetApp'

createRoot(document.getElementById('root')!).render(<StrictMode><IntranetApp/></StrictMode>)
