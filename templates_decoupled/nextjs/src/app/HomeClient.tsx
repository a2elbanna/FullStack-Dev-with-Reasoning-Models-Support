'use client';

import Header from '@/components/Header';
import Hero from '@/components/Hero';
import Features from '@/components/Features';
import Footer from '@/components/Footer';
import ApiCallButton from '@/components/ApiCallButton';

export default function HomeClient() {
  return (
    <div className="min-h-screen flex flex-col bg-gradient-to-br from-blue-50 to-indigo-100">
      <Header />
      <main className="flex-grow">
        <Hero />
        <Features />
        {/* Additional sections can be added here */}
        <section id="get-started" className="py-16 bg-white">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="bg-gradient-to-r from-indigo-500 to-purple-600 rounded-2xl p-8 md:p-12 shadow-xl">
              <div className="max-w-3xl mx-auto text-center">
                <h2 className="text-3xl md:text-4xl font-bold text-white">
                  Ready to Get Started?
                </h2>
                <p className="mt-4 text-xl text-indigo-100 max-w-2xl mx-auto">
                  Launch your next project faster with our Next.js template. Everything you need is already configured.
                </p>
                <div className="mt-8">
                  <a 
                    href="#" 
                    className="inline-block bg-white text-indigo-600 px-8 py-4 rounded-lg font-medium hover:bg-gray-100 transition-colors duration-200 shadow-lg hover:shadow-xl transform hover:-translate-y-1 transition-transform duration-200"
                  >
                    Download Template
                  </a>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* API Call Section */}
        <section className="py-16 bg-gray-50">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="bg-white rounded-2xl p-8 shadow-lg">
              <div className="text-center">
                <h2 className="text-3xl font-bold text-gray-900">Backend API Integration</h2>
                <p className="mt-4 text-lg text-gray-600">
                  Click the button below to call the backend API and display the response
                </p>

                <div className="mt-8">
                  <ApiCallButton />
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>
      <Footer />
    </div>
  );
}