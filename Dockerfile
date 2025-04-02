FROM node:16-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

# Berechtigungsproblem beheben: Stelle sicher, dass alle Dateien dem node-Benutzer gehören
RUN chown -R node:node /app
USER node

EXPOSE 3000

CMD ["npm", "start"]