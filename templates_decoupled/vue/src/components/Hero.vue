<template>
  <section class="py-16 md:py-24 bg-gradient-to-r from-indigo-50 to-blue-100">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="text-center">
        <h1 class="text-4xl md:text-5xl lg:text-6xl font-bold text-gray-900 leading-tight">
          Build Modern Web Applications with Ease
        </h1>
        <p class="mt-6 text-xl text-gray-600 max-w-2xl mx-auto">
          A modern, responsive web application built with Vue to help you launch your projects faster.
        </p>
        <div class="mt-10 flex flex-col sm:flex-row gap-4 justify-center">
          <a
            href="#get-started"
            @click.prevent="handleScroll('get-started')"
            class="bg-indigo-600 text-white px-8 py-4 rounded-lg font-medium hover:bg-indigo-700 transition-colors duration-200 shadow-md hover:shadow-lg transform hover:-translate-y-1 transition-transform duration-200 text-center"
          >
            Get Started
          </a>
          <a
            href="#features"
            @click.prevent="handleScroll('features')"
            class="bg-white text-indigo-600 border border-indigo-200 px-8 py-4 rounded-lg font-medium hover:bg-indigo-50 transition-colors duration-200 shadow-sm hover:shadow-md text-center"
          >
            Learn More
          </a>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
// Define emits for parent to handle scrolling
const emit = defineEmits(['scrollToSection']);

const handleScroll = (sectionId: string) => {
  emit('scrollToSection', sectionId);
};
</script>