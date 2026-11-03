<template>
  <section id="features" class="py-16 bg-white">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="text-center">
        <h2 class="text-3xl md:text-4xl font-bold text-gray-900">
          Powerful Features for Modern Development
        </h2>
        <p class="mt-4 text-xl text-gray-600 max-w-3xl mx-auto">
          Everything you need to build scalable, maintainable web applications with best practices.
        </p>
      </div>

      <div class="mt-16 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-10">
        <div
          v-for="(feature, index) in features"
          :key="index"
          class="bg-gradient-to-br from-white to-gray-50 rounded-xl p-8 shadow-md hover:shadow-lg transition-shadow duration-300 border border-gray-100"
        >
          <div class="text-indigo-600 bg-indigo-50 w-16 h-16 rounded-lg flex items-center justify-center mb-6">
            <component :is="feature.icon" />
          </div>
          <h3 class="text-xl font-semibold text-gray-900 mb-3">
            {{ feature.title }}
          </h3>
          <p class="text-gray-600">
            {{ feature.description }}
          </p>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { h } from 'vue';

// Define SVG icons as functions
const NextJSIcon = () => h(
  'svg',
  {
    xmlns: 'http://www.w3.org/2000/svg',
    class: 'h-8 w-8 text-indigo-600',
    fill: 'none',
    viewBox: '0 0 24 24',
    stroke: 'currentColor'
  },
  [
    h('path', {
      'stroke-linecap': 'round',
      'stroke-linejoin': 'round',
      'stroke-width': 2,
      d: 'M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z'
    })
  ]
);

const ReactIcon = () => h(
  'svg',
  {
    xmlns: 'http://www.w3.org/2000/svg',
    class: 'h-8 w-8 text-indigo-600',
    fill: 'none',
    viewBox: '0 0 24 24',
    stroke: 'currentColor'
  },
  [
    h('path', {
      'stroke-linecap': 'round',
      'stroke-linejoin': 'round',
      'stroke-width': 2,
      d: 'M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4'
    })
  ]
);

const ResponsiveIcon = () => h(
  'svg',
  {
    xmlns: 'http://www.w3.org/2000/svg',
    class: 'h-8 w-8 text-indigo-600',
    fill: 'none',
    viewBox: '0 0 24 24',
    stroke: 'currentColor'
  },
  [
    h('path', {
      'stroke-linecap': 'round',
      'stroke-linejoin': 'round',
      'stroke-width': 2,
      d: 'M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z'
    })
  ]
);

const TailwindIcon = () => h(
  'svg',
  {
    xmlns: 'http://www.w3.org/2000/svg',
    class: 'h-8 w-8 text-indigo-600',
    fill: 'none',
    viewBox: '0 0 24 24',
    stroke: 'currentColor'
  },
  [
    h('path', {
      'stroke-linecap': 'round',
      'stroke-linejoin': 'round',
      'stroke-width': 2,
      d: 'M7 21a4 4 0 01-4-4V5a2 2 0 002-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01'
    })
  ]
);

const PerformanceIcon = () => h(
  'svg',
  {
    xmlns: 'http://www.w3.org/2000/svg',
    class: 'h-8 w-8 text-indigo-600',
    fill: 'none',
    viewBox: '0 0 24 24',
    stroke: 'currentColor'
  },
  [
    h('path', {
      'stroke-linecap': 'round',
      'stroke-linejoin': 'round',
      'stroke-width': 2,
      d: 'M13 10V3L4 14h7v7l9-11h-7z'
    })
  ]
);

const SeoIcon = () => h(
  'svg',
  {
    xmlns: 'http://www.w3.org/2000/svg',
    class: 'h-8 w-8 text-indigo-600',
    fill: 'none',
    viewBox: '0 0 24 24',
    stroke: 'currentColor'
  },
  [
    h('path', {
      'stroke-linecap': 'round',
      'stroke-linejoin': 'round',
      'stroke-width': 2,
      d: 'M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9'
    })
  ]
);

const features = [
  {
    title: "Vue Framework",
    description: "Reactive data binding, component-based architecture, and efficient virtual DOM updates.",
    icon: NextJSIcon
  },
  {
    title: "Vue Components",
    description: "Modern component-based architecture with reusable UI elements and state management.",
    icon: ReactIcon
  },
  {
    title: "Reactivity System",
    description: "Intuitive reactivity system that automatically tracks dependencies and updates the DOM efficiently.",
    icon: ResponsiveIcon
  },
  {
    title: "Tailwind CSS",
    description: "Utility-first CSS framework for rapidly building custom user interfaces without writing custom CSS.",
    icon: TailwindIcon
  },
  {
    title: "Performance Optimized",
    description: "Efficient virtual DOM implementation and component-based architecture for optimal performance.",
    icon: PerformanceIcon
  },
  {
    title: "Developer Experience",
    description: "Intuitive API, detailed documentation, and excellent tooling for a smooth development experience.",
    icon: SeoIcon
  }
];
</script>