'use client';

import Link from 'next/link';

export default function Hero() {
  return (
    <section className="py-16 md:py-24 bg-gradient-to-r from-indigo-50 to-blue-100">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center">
          <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold text-gray-900 leading-tight">
            Build Modern Web Applications with Ease
          </h1>
          <p className="mt-6 text-xl text-gray-600 max-w-2xl mx-auto">
            A powerful full-stack template built with Next.js, NestJS, TypeScript, and PostgreSQL to help you launch your projects faster.
          </p>
          <div className="mt-10 flex flex-col sm:flex-row gap-4 justify-center">
            <Link 
              href="#get-started" 
              className="bg-indigo-600 text-white px-8 py-4 rounded-lg font-medium hover:bg-indigo-700 transition-colors duration-200 shadow-md hover:shadow-lg transform hover:-translate-y-1 transition-transform duration-200 text-center"
            >
              Get Started
            </Link>
            <Link 
              href="#features" 
              className="bg-white text-indigo-600 border border-indigo-200 px-8 py-4 rounded-lg font-medium hover:bg-indigo-50 transition-colors duration-200 shadow-sm hover:shadow-md text-center"
            >
              Learn More
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}