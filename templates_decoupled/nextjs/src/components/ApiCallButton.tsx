'use client';

import { useState } from 'react';
import { api } from '@/lib/api';

export default function ApiCallButton() {
  const [response, setResponse] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleClick = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const result = await api.get('/hello', {
        responseType: 'text' // Expecting a text response
      });
      setResponse(result.data);
    } catch (err) {
      console.error('Error calling API:', err);
      setError('Failed to fetch data from the API');
      setResponse(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mt-8">
      <button
        onClick={handleClick}
        disabled={loading}
        className={`px-6 py-3 rounded-lg font-medium transition-colors duration-200 ${
          loading
            ? 'bg-gray-400 cursor-not-allowed'
            : 'bg-indigo-600 hover:bg-indigo-700 text-white'
        }`}
      >
        {loading ? 'Loading...' : 'Call API'}
      </button>

      {error && (
        <div className="mt-4 p-4 bg-red-100 text-red-700 rounded-lg">
          {error}
        </div>
      )}

      {response && (
        <div className="mt-4 p-4 bg-green-100 text-green-700 rounded-lg">
          <strong>Response:</strong> {response}
        </div>
      )}
    </div>
  );
}