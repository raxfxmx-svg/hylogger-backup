'use client';
import { useEffect, useState } from 'react';
import { api } from './v1';

export function useCatalogue() {
  const [state, setState] = useState({ holes: [], loading: true, error: null });
  useEffect(() => {
    let active = true;
    api.holes().then(holes => active && setState({ holes, loading: false, error: null }))
      .catch(error => active && setState({ holes: [], loading: false, error: error.message }));
    return () => { active = false; };
  }, []);
  return state;
}
