<template>
  <header class="bg-white shadow-sm sticky top-0 z-50">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="flex justify-between h-16 items-center">
        <div class="flex items-center">
          <a href="/" class="text-2xl font-bold text-indigo-600 flex items-center">
            <span>MyApp</span>
          </a>
        </div>

        <!-- Desktop Navigation -->
        <nav class="hidden md:flex space-x-8">
          <a href="#top" @click.prevent="scrollToTop()" class="text-gray-700 hover:text-indigo-600 font-medium transition-colors duration-200">
            Home
          </a>
          <a href="#features" @click.prevent="scrollToSection('features')" class="text-gray-700 hover:text-indigo-600 font-medium transition-colors duration-200">
            Features
          </a>
          <a href="#contact" @click.prevent="scrollToSection('contact')" class="text-gray-700 hover:text-indigo-600 font-medium transition-colors duration-200">
            Contact
          </a>
        </nav>

        <!-- CTA Button - Hidden on mobile -->
        <div class="hidden md:block">
          <a
            href="#get-started"
            @click.prevent="scrollToSection('get-started')"
            class="bg-indigo-600 text-white px-5 py-2 rounded-md font-medium hover:bg-indigo-700 transition-colors duration-200 shadow-sm hover:shadow-md"
          >
            Get Started
          </a>
        </div>

        <!-- Mobile menu button -->
        <div class="md:hidden">
          <button
            @click="toggleMenu"
            class="text-gray-700 hover:text-indigo-600 focus:outline-none"
          >
            <svg v-if="!isMenuOpen" xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-gray-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
            </svg>
            <svg v-else xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-gray-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      <!-- Mobile Navigation -->
      <div v-if="isMenuOpen" class="md:hidden py-4 border-t border-gray-200">
        <div class="flex flex-col space-y-3">
          <a
            href="#top"
            @click.prevent="scrollToTop(); closeMenu()"
            class="text-gray-700 hover:text-indigo-600 font-medium py-2 px-4 rounded-md hover:bg-gray-50 transition-colors duration-200"
          >
            Home
          </a>
          <a
            href="#features"
            @click.prevent="scrollToSection('features'); closeMenu()"
            class="text-gray-700 hover:text-indigo-600 font-medium py-2 px-4 rounded-md hover:bg-gray-50 transition-colors duration-200"
          >
            Features
          </a>
          <a
            href="#contact"
            @click.prevent="scrollToSection('contact'); closeMenu()"
            class="text-gray-700 hover:text-indigo-600 font-medium py-2 px-4 rounded-md hover:bg-gray-50 transition-colors duration-200"
          >
            Contact
          </a>
          <a
            href="#get-started"
            @click.prevent="scrollToSection('get-started'); closeMenu()"
            class="bg-indigo-600 text-white px-5 py-2 rounded-md font-medium hover:bg-indigo-700 transition-colors duration-200 text-center mt-2"
          >
            Get Started
          </a>
        </div>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { ref } from 'vue';

const isMenuOpen = ref(false);

const toggleMenu = () => {
  isMenuOpen.value = !isMenuOpen.value;
};

const closeMenu = () => {
  isMenuOpen.value = false;
};

const scrollToSection = (sectionId: string) => {
  closeMenu();
  setTimeout(() => {
    const element = document.getElementById(sectionId) || document.querySelector(`#${sectionId}`);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth' });
    }
  }, 100);
};

const scrollToTop = () => {
  closeMenu();
  window.scrollTo({ top: 0, behavior: 'smooth' });
};
</script>