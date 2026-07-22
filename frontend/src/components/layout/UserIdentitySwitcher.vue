<script setup lang="ts">
import { DownOutlined } from '@ant-design/icons-vue'
import { storeToRefs } from 'pinia'

import { useUserStore } from '@/store/userStore'

const userStore = useUserStore()
const { currentUserComputed, loadingRef, usersRef } = storeToRefs(userStore)
</script>

<template>
  <a-dropdown :trigger="['click']" placement="bottomRight">
    <button class="user-profile" type="button" :disabled="loadingRef">
      <a-avatar size="small" class="user-avatar">
        {{ currentUserComputed?.role_name.slice(0, 1) || '用' }}
      </a-avatar>
      <span>
        <strong>{{ currentUserComputed?.display_name || '加载项目用户' }}</strong>
        <small>{{ currentUserComputed?.role_name || '身份未就绪' }}</small>
      </span>
      <DownOutlined />
    </button>
    <template #overlay>
      <a-menu :selected-keys="[currentUserComputed?.user_code || '']">
        <a-menu-item
          v-for="user in usersRef"
          :key="user.user_code"
          @click="userStore.setCurrentUser(user.user_code)"
        >
          <span class="identity-option">
            <strong>{{ user.display_name }}</strong>
            <small>{{ user.role_name }}</small>
          </span>
        </a-menu-item>
      </a-menu>
    </template>
  </a-dropdown>
</template>

<style scoped lang="less">
.user-profile {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 0 0 0 14px;
  color: #fff;
  cursor: pointer;
  background: transparent;
  border: 0;
  border-left: 1px solid rgb(255 255 255 / 10%);
}

.user-profile:disabled {
  cursor: wait;
  opacity: 0.7;
}

.user-profile > span,
.identity-option {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

.user-avatar {
  color: #17372a;
  background: #a9d9bd;
}

.user-profile strong {
  font-size: 11px;
  font-weight: 500;
  line-height: 15px;
}

.user-profile small {
  font-size: 9px;
  line-height: 12px;
  color: rgb(255 255 255 / 46%);
}

.user-profile > :last-child {
  font-size: 9px;
  color: rgb(255 255 255 / 42%);
}

.identity-option strong {
  font-size: 12px;
  font-weight: 500;
}

.identity-option small {
  font-size: 10px;
  color: #8a958f;
}
</style>
