import { useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { postJson } from '../api'
import type { DiseaseEvent } from '../types'
import EventsPage from './EventsPage'

export default function InternetEventsPage({events,onCollected}:{events:DiseaseEvent[];onCollected:()=>void}){
  const[collecting,setCollecting]=useState(false)
  const collect=async()=>{setCollecting(true);try{await postJson('/sources/run',{});onCollected()}finally{setCollecting(false)}}
  const action=<button className="secondary-button" disabled={collecting} onClick={collect}><RefreshCw className={collecting?'spin':''} size={16}/>{collecting?'正在采集':'立即采集'}</button>
  return <EventsPage events={events} actions={action}/>
}
