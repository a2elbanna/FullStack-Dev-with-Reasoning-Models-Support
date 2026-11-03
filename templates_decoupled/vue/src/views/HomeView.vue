<script setup lang="ts">
import { onMounted } from 'vue';
import Header from '@/components/Header.vue';
import Hero from '@/components/Hero.vue';
import Features from '@/components/Features.vue';
import Footer from '@/components/Footer.vue';
import ApiCallButton from '@/components/ApiCallButton.vue';

const scrollToSection = (sectionId: string) => {
  setTimeout(() => {
    const element = document.getElementById(sectionId) || document.querySelector(`#${sectionId}`);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth' });
    }
  }, 100);
};

// Listen for hash changes in URL to handle direct linking
onMounted(() => {
  if (location.hash) {
    const hash = location.hash.substring(1); // Remove '#' symbol
    scrollToSection(hash);
  }
});
</script>

<template>
  <div id="top" class="min-h-screen flex flex-col bg-gradient-to-br from-blue-50 to-indigo-100">
    <Header />
    <main class="flex-grow">
      <Hero @scroll-to-section="scrollToSection" />
      <div id="features">
        <Features />
      </div>
      <!-- Additional sections can be added here -->
      <section id="get-started" class="py-16 bg-white">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div class="bg-gradient-to-r from-indigo-500 to-purple-600 rounded-2xl p-8 md:p-12 shadow-xl">
            <div class="max-w-3xl mx-auto text-center">
              <h2 class="text-3xl md:text-4xl font-bold text-white">
                Ready to Get Started?
              </h2>
              <p class="mt-4 text-xl text-indigo-100 max-w-2xl mx-auto">
                Launch your next project faster with our Vue template. Everything you need is already configured.
              </p>
              <div class="mt-8">
                <a
                  href="#"
                  class="inline-block bg-white text-indigo-600 px-8 py-4 rounded-lg font-medium hover:bg-gray-100 transition-colors duration-200 shadow-lg hover:shadow-xl transform hover:-translate-y-1 transition-transform duration-200"
                >
                  Download Template
                </a>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- API Call Section -->
      <section class="py-16 bg-gray-50">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div class="bg-white rounded-2xl p-8 shadow-lg">
            <div class="text-center">
              <h2 class="text-3xl font-bold text-gray-900">Backend API Integration</h2>
              <p class="mt-4 text-lg text-gray-600">
                Click the button below to call the backend API and display the response
              </p>

              <div class="mt-8">
                <ApiCallButton />
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>
    <Footer id="contact" />
  </div>
</template>
