describe('Administrative Actions', function() {
  beforeEach(() => {
    // reset and seed the database prior to every test
    cy.request('/test/reset_db')

    // seed a user in the DB that we can control from our tests
    cy.request('POST', '/test/seed/user', { 
      username: 'adminUser',
      first_name: 'Jane',
      last_name: 'Addy',
      instructor: true,
      admin: true,
    }).its('body')
      .as('currentUser')

    cy.login('adminUser', 'testing')
  })

  describe('Instructors', function() {
    /*
    beforeEach(function() {
    })
    */

    it('Create New Instructor', function () {
      cy.visit('/')
      cy.contains("Admin").click()
      cy.contains("Instructors").click()

      cy.location('pathname').should('eq', '/admin/instructors')
      cy.get('tr').should('have.length', 2)
      cy.get('table').contains('adminuser')

      // add a new instructor using the form
      cy.get('input[name=first_name]').type("Smarty")
      cy.get('input[name=last_name]').type("Pants")
      cy.get('input[name=username]').type("spants")
      cy.contains("Create Instructor").click()

      cy.location('pathname').should('eq', '/admin/instructors')
      cy.contains("Added new instructor: Smarty Pants")
      cy.get('tr').should('have.length', 3)
      cy.get('table').contains("Smarty")
      cy.get('table').contains("Pants")
      cy.get('table').contains("spants")


      /*
      cy.get('input[name=title]').type("Intro to Narwhals")
      cy.get('textarea[name=description]').type("A very interesting course")
      cy.get('input[name=start_date]').type('2021-01-03')
      cy.get('input[name=end_date]').type('2095-07-13')

      // TODO: check URL to make sure we are at setup textbooks
      cy.get('input[id=textbookSearchBar]').type(`${this.textbook1.title}{enter}`)
      cy.contains('button', 'Add').click()
      cy.contains("Continue...").click()
      cy.contains("Next Step").click()

      // TODO: check url to make sure we are at setup topics
      cy.get('[data-cy=topicList]').as('sectionTopics')

      // Add all topics from first section and one from the third section
      cy.get('@sectionTopics').first().contains("Add All").click()
      cy.get('[data-cy=topicsPage]').children().should('have.length', 3)

      cy.contains(this.textbook1.sections[2].topics[1].text).click()
      cy.get('[data-cy=topicsPage]').children().should('have.length', 4)

      // remove one of the topics
      cy.get('[data-cy=topicsPage]').children().eq(1).contains("Remove").click()

      cy.contains("Search / Create").click()

      // search for non-existent topic and add it through here
      cy.get('#topicSearchBar').type("aaabbb{enter}")
      cy.contains("Create and Add Topic").click()
      cy.get("#courseTopics").should('contain', 'aaabbb')

      cy.get('#topicSearchBar').type(`{selectAll}{backspace}${this.extraTopics[0].text}{enter}`)
      cy.get('[data-cy=result0]').should('contain', this.extraTopics[0].text).find('button').click()

      cy.get('#courseTopics').should('contain', this.extraTopics[0].text)
      cy.contains("Continue...").click()
      cy.contains("Exit Course Setup").click()

      cy.location('pathname').should('eq', `/c/test-course1`)
      */
    })

    it('Create New Section', function () {
      cy.request('POST', '/test/seed/user', { 
        username: 'instructor1',
        first_name: 'Joe',
        last_name: 'Instructor',
        instructor: true,
      })

      cy.visit('/admin/sections')
      cy.get('tr').should('have.length', 1)

      // create a new section with the two existing instructors
      cy.get('input[name=section_num]').type("1")
      cy.contains('Addy, Jane').click()
      cy.contains('Instructor, Joe').click()
      cy.contains('Create Section').click()

      cy.location('pathname').should('eq', '/admin/sections')
      cy.get('tr').should('have.length', 2)
      cy.get('table').contains("Jane Addy")
      cy.get('table').contains("Joe Instructor")

      // remove one of the instructors from the section
      cy.contains('Modify').click()
      cy.location('pathname').should('eq', '/admin/sections/modify')

      cy.contains('Instructor, Joe').click()
      cy.contains('Update Instructors').click()
      cy.location('pathname').should('eq', '/admin/sections/modify')

      cy.contains('Cancel').click()
      cy.location('pathname').should('eq', '/admin/sections')
      cy.get('table').should('not.contain', 'Joe Instructor')

      cy.get('nav').contains('Courses').click()
      cy.get('nav').contains('Section 1').click()

      cy.location('pathname').should('eq', '/comp110/sp21/s1/')
      cy.get('tr').should('have.length', 2)

      cy.contains('Upload Roster File').click()
      cy.get('input[name=roster_file]').selectFile('cypress/fixtures/text_files/roster1.csv')
      cy.get('#uploadRosterModal').find('input[name=submit]').click()

      cy.get('tr').should('have.length', 11)

    })
  })
})

