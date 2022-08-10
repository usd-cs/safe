// ***********************************************
// This example commands.js shows you how to
// create various custom commands and overwrite
// existing commands.
//
// For more comprehensive examples of custom
// commands please read more here:
// https://on.cypress.io/custom-commands
// ***********************************************
//
//
// -- This is a parent command --

// Log in without using the UI
Cypress.Commands.add('login', (username, password) => {
    cy.request({
      url: `/auth/verify_ticket?ticket=ST-mock-${username}`,
	  followRedirect: false,
    }).then((resp) => {
	  expect(resp.status).to.eq(302)
	  expect(resp.redirectedToUrl).to.eq(Cypress.config().baseUrl + '/')
    })
})


//
//
// -- This is a child command --
// Cypress.Commands.add('drag', { prevSubject: 'element'}, (subject, options) => { ... })
//
//
// -- This is a dual command --
// Cypress.Commands.add('dismiss', { prevSubject: 'optional'}, (subject, options) => { ... })
//
//
// -- This will overwrite an existing command --
// Cypress.Commands.overwrite('visit', (originalFn, url, options) => { ... })
