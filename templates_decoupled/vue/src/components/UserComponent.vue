<script setup lang="ts">
import { ref } from 'vue';
import { apiService } from '@/services/api';

const helloMessage = ref<string>('');
const loading = ref(false);
const error = ref<string | null>(null);

const fetchHello = async () => {
  loading.value = true;
  error.value = null;

  try {
    // This request will be proxied to http://localhost:3001/api/hello during development
    const message = await apiService.getHello();
    helloMessage.value = message;
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to fetch hello message';
  } finally {
    loading.value = false;
  }
};
</script>

<template>
  <div class="hello-api-demo">
    <h1>Hello World API Demo</h1>

    <button @click="fetchHello" :disabled="loading">Test Backend Connection</button>

    <div v-if="loading">Loading...</div>
    <div v-if="error" class="error">{{ error }}</div>

    <div v-if="!loading && !error && helloMessage" class="message">
      {{ helloMessage }}
    </div>
  </div>
</template>

<style scoped>
.hello-api-demo {
  padding: 2rem;
  text-align: center;
}

.error {
  color: red;
  margin: 1rem 0;
}

.message {
  font-size: 1.2rem;
  font-weight: bold;
  margin: 1rem 0;
  padding: 1rem;
  background-color: #f0f0f0;
  border-radius: 4px;
}
</style>