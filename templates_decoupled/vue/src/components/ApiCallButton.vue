<template>
  <div class="mt-8">
    <button
      @click="handleClick"
      :disabled="loading"
      :class="[
        'px-6 py-3 rounded-lg font-medium transition-colors duration-200',
        loading
          ? 'bg-gray-400 cursor-not-allowed'
          : 'bg-indigo-600 hover:bg-indigo-700 text-white'
      ]"
    >
      {{ loading ? 'Loading...' : 'Call API' }}
    </button>

    <div v-if="error" class="mt-4 p-4 bg-red-100 text-red-700 rounded-lg">
      {{ error }}
    </div>

    <div v-if="response" class="mt-4 p-4 bg-green-100 text-green-700 rounded-lg">
      <strong>Response:</strong> {{ response }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { apiService } from '@/services/api';

const response = ref<string | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

const handleClick = async () => {
  loading.value = true;
  error.value = null;
  
  try {
    const result = await apiService.getHello();
    response.value = result;
  } catch (err) {
    console.error('Error calling API:', err);
    error.value = 'Failed to fetch data from the API';
    response.value = null;
  } finally {
    loading.value = false;
  }
};
</script>