import { API_BASE } from '@/config';
import { createV1Client } from './v1-client.cjs';
export const api = createV1Client(API_BASE);
