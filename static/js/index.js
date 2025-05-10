window.addEventListener('load', () => {
    // Connect Teacher Box to the Ellipse
    new LeaderLine(
        document.querySelector('.teacher-img'),
        document.querySelector('.ellipse-6'),
        {
            color: '#CA7979',    // Teacher color
            size: 5,
            path: 'arc',         // 'arc' for a curved line
            startPlug: 'behind', // Option: 'behind' keeps it clean
            endPlug: 'behind',   // Adds an arrowhead at the end
            endPlugSize: 1.5
        }
    );

    // Connect Student Box to the Ellipse
    new LeaderLine(
        document.querySelector('.student-img'),
        document.querySelector('.ellipse-6'),
        {
            color: '#E9B384',    // Student color
            size: 5,
            path: 'arc',
            startPlug: 'behind',
            endPlug: 'behind'
        }
    );

    // Connect Institute Box to the Ellipse
    new LeaderLine(
        document.querySelector('.institute-img'),
        document.querySelector('.ellipse-6'),
        {
            color: '#A1CCD1',    // Institute color
            size: 5,
            path: 'arc',
            startPlug: 'arrow3',
            endPlug: 'behind',
            endPlugSize: 1.5
        }
    );
});
