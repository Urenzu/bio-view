export type User = {
  id: number;
  email: string;
  name: string;
  picture: string;
};

export type Hit = {
  doi: string;
  version: number;
  section: string;
  title: string;
  source: string;
  subject: string;
  posted_date: string;
  authors: string;
  text: string;
  score: number;
};

export type AskRequest = {
  query: string;
  conversation_id?: number;
  sources?: string[];
  subjects?: string[];
  date_from?: string;
  date_to?: string;
};
