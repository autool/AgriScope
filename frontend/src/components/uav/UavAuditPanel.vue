<script setup lang="ts">
import type { UavEvent } from '@/types/uav'

defineProps<{
  events: UavEvent[]
}>()
</script>

<template>
  <section class="audit-panel">
    <header>
      <div>
        <small>IMMUTABLE AUDIT</small>
        <h3>无人机任务审计轨迹</h3>
      </div>
      <a-tag>{{ events.length }} 条</a-tag>
    </header>
    <div class="event-list">
      <article v-for="event in events" :key="`${event.entity_type}-${event.entity_code}-${event.event_type}-${event.created_at}`">
        <span>
          <strong>{{ event.event_type }}</strong>
          <em>{{ event.entity_type }} · {{ event.entity_code }}</em>
        </span>
        <span class="actor">{{ event.actor }} · {{ event.actor_role }}</span>
        <time>{{ new Date(event.created_at).toLocaleString('zh-CN') }}</time>
      </article>
      <a-empty v-if="!events.length" description="尚无无人机业务事件；系统不会生成固定审计记录" />
    </div>
  </section>
</template>

<style scoped>
.audit-panel { display: flex; min-height: 0; flex-direction: column; padding: 10px 12px; overflow: hidden; background: #fff; border: 1px solid #dfe5e2; border-radius: 8px; }
header { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 7px; }
small { font-size: 8px; color: #718078; letter-spacing: 1px; }
h3 { margin: 2px 0 0; font-size: 14px; color: #20352c; }
.event-list { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; min-height: 0; overflow: auto; }
article { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 3px 8px; padding: 7px 8px; background: #f8faf9; border: 1px solid #e4e9e6; border-radius: 6px; }
article > span:first-child { display: flex; min-width: 0; flex-direction: column; }
strong { font-size: 10px; color: #294137; }
em, .actor, time { overflow: hidden; font-size: 8px; font-style: normal; color: #7c8a83; text-overflow: ellipsis; white-space: nowrap; }
time { grid-column: 1 / -1; }
@media (max-width: 1320px) { .event-list { grid-template-columns: 1fr 1fr; } }
</style>
