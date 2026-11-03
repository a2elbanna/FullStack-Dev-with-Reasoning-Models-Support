import { ref } from 'vue';

// Base URL for API requests
// During development, requests are proxied through Vite to http://localhost:3001
// In production, requests will go directly to the VITE_API_BASE_URL
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

/**
 * Creates a base API request function with common headers and error handling
 */
export const apiRequest = async (endpoint: string, options: RequestInit = {}) => {
  // For the hello world API, we use the base URL directly
  const url = endpoint.startsWith('/') ? `${API_BASE_URL}${endpoint}` : `${API_BASE_URL}/${endpoint}`;

  const config: RequestInit = {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  };

  try {
    const response = await fetch(url, config);

    if (!response.ok) {
      throw new Error(`HTTP error! Status: ${response.status}`);
    }

    // For requests that don't return content
    if (response.status === 204 || response.headers.get('content-length') === '0') {
      return null;
    }

    return await response.text(); // Hello world API returns plain text
  } catch (error) {
    console.error('API request failed:', error);
    throw error;
  }
};

/**
 * Simple API service for the hello world API
 */
export const apiService = {
  // GET request to the hello world endpoint
  getHello: () => {
    return apiRequest('/hello', { method: 'GET' }); // This will be proxied to http://localhost:3001/api/hello
  },
};

// Example usage:
// const helloMessage = await apiService.getHello();